from django.conf import settings
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.http import Http404, HttpResponse, HttpResponseForbidden, HttpResponseBadRequest
from django.shortcuts import render, get_object_or_404
from django.template.context import RequestContext
from django.template.loader import get_template
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from eulcommon.djangoextras.http import HttpResponseSeeOtherRedirect
from eulfedora.models import DigitalObjectSaveFailure
from eulfedora.server import Repository
from eulfedora.util import RequestFailed, PermissionDenied
from eulfedora.views import raw_datastream
import json
from sunburnt import sunburnt

from openemory.accounts.auth import login_required
from openemory.harvest.models import HarvestRecord
from openemory.publication.forms import UploadForm, DublinCoreEditForm
from openemory.publication.models import Article
from openemory.util import md5sum, solr_interface


@login_required
@require_http_methods(['GET', 'POST'])
def ingest(request):
    '''Create a new :class:`~openemory.publication.models.Article`
    object and ingest into the repository one of two ways:

      * By uploading a file from a web form.  On GET, displays the
        upload form.  On POST with a valid file, ingests the content
        into Fedora.

      * When a request is POSTed via AJAX, looks for a pmcid in the
        request to find the
        :class:`~openemory.harvest.models.HarvestRecord` to be
        ingested.  Requires site admin permissions.
      
    '''
    context = {}
    if request.method == 'POST':
        # init repo with request to use logged-in user credentials for fedora access
        repo = Repository(request=request)

        # ajax request: should pass pmcid for HarvestRecord to be ingested
        if request.is_ajax():
            if 'pmcid' not in request.POST or not request.POST['pmcid']:
                return HttpResponseBadRequest('No record specified for ingest',
                                              mimetype='text/plain')
            record = get_object_or_404(HarvestRecord, pmcid=request.POST['pmcid'])
            if not record.ingestable:
                return HttpResponseBadRequest('Record cannot be ingested',
                                              mimetype='text/plain')
            # check that user has required permissions
            if not request.user.has_perm('harvest.ingest_harvestrecord'):
                return HttpResponseForbidden('Permission Denied',
                                             mimetype='text/plain')
                
            # initialize a new article object from the harvest record
            obj = record.as_publication_article(repo=repo)
            try:
                saved = obj.save('Ingest from harvested record PubMed Central %d' % \
                                 record.pmcid)
                if saved:
                    # mark the database record as ingested
                    record.mark_ingested()
                    # return a 201 Created with new location
                    response = HttpResponse('Ingested as %s' % obj.pid,
                                            mimetype='text/plain',
                                            status=201)
                    # return a location for the newly created object
                    # (should really be a display view when we have one)
                    response['Location'] = reverse('publication:edit',
                                                   kwargs={'pid': obj.pid})
                    return response
            except RequestFailed as rf:
                return HttpResponse('Error: %s' % rf,
                                    mimetype='text/plain', status=500)
                
        # otherwise, assume form data was POSTed and handle as upload form
        else:
            form = UploadForm(request.POST, request.FILES)
            if form.is_valid():
                obj = repo.get_object(type=Article)
                # TODO: move init logic into an Article class method? 
                uploaded_file = request.FILES['pdf']
                # use filename as preliminary title
                obj.label = uploaded_file.name
                # copy object label into dc:title
                obj.dc.content.title = obj.label
                # set the username of the currently-logged in user as object owner
                obj.owner = request.user.username
                # set uploaded file as pdf datastream content
                obj.pdf.content = uploaded_file
                # for now, use the content type passed by the browser (even though we know it is unreliable)
                # eventually, we'll want to use mime magic to inspect files before ingest
                obj.pdf.mimetype = uploaded_file.content_type 
                obj.dc.content.format = obj.pdf.mimetype
                # calculate MD5 checksum for the uploaded file before ingest
                obj.pdf.checksum = md5sum(uploaded_file.temporary_file_path())
                obj.pdf.checksum_type = 'MD5'
                try:
                    saved = obj.save('upload via OpenEmory')
                    if saved:
                        messages.success(request,
                            'Successfully uploaded article PDF <%(tag)s>%(file)s</%(tag)s>; saved as <%(tag)s>%(pid)s</%(tag)s>' \
                                         % {'file': uploaded_file.name, 'pid': obj.pid, 'tag': 'strong'})
                        next_url = reverse('accounts:profile',
                                           kwargs={'username': request.user.username })
                        return HttpResponseSeeOtherRedirect(next_url)
                except RequestFailed as rf:
                    context['error'] = rf
            
    else:
        # init unbound form for display
        form = UploadForm()
        
    context['form'] = form

    return render(request, 'publication/upload.html', context)


@login_required()
def edit_metadata(request, pid):
    """View to edit the metadata for an existing
    :class:`~openemory.publication.models.Article` .

    On GET, display the form.  When valid form data is POSTed, updates
    thes object.
    """
    # response status should be 200 unless something goes wrong
    status_code = 200
    # init the object as the appropriate type
    try:
        repo = Repository(request=request)
        obj = repo.get_object(pid=pid, type=Article)
        if not obj.exists:
            raise Http404
    except RequestFailed:
        raise Http404

    if request.user.username != obj.owner:
        tpl = get_template('403.html')
        return HttpResponseForbidden(tpl.render(RequestContext(request)))


    # on GET, instantiate the form with existing object data (if any)
    if request.method == 'GET':
        form = DublinCoreEditForm(instance=obj.dc.content)

    elif request.method == 'POST':
        form = DublinCoreEditForm(request.POST, instance=obj.dc.content)
        if form.is_valid():
            form.update_instance()
            # also use dc:title as object label
            obj.label = obj.dc.content.title
            try:
                obj.save('updated metadata')
                messages.success(request,'Successfully updated %s - %s' % (obj.label, obj.pid))

                # maybe redirect to article view page when we have one
                return HttpResponseSeeOtherRedirect(reverse('site-index'))
            except (DigitalObjectSaveFailure, RequestFailed) as rf:
                # do we need a different error message for DigitalObjectSaveFailure?
                if isinstance(rf, PermissionDenied):
                    msg = 'You don\'t have permission to modify this object in the repository.'
                else:
                    msg = 'There was an error communicating with the repository.'
                messages.error(request,
                               msg + ' Please contact a site administrator.')

                # pass the fedora error code (if any) back in the http response
                if hasattr(rf, 'code'):
                    status_code = getattr(rf, 'code')
    return render(request, 'publication/dc_edit.html', {'form': form, 'obj': obj},
      status=status_code)


def download_pdf(request, pid):
    '''View to allow access the PDF datastream of a
    :class:`openemory.publication.models.Article` object.  Sets a
    content-disposition header that will prompt the file to be saved
    with a default title based on the object label.
    '''
    repo = Repository(request=request)
    try:
        # retrieve the object so we can use it to set the download filename
        obj = repo.get_object(pid, type=Article)
        extra_headers = {
            # generate a default filename based on the object
            # FIXME: what do we actually want here? ARK noid?
            'Content-Disposition': "attachment; filename=%s.pdf" % obj.pid
        }
        # use generic raw datastream view from eulfedora
        return raw_datastream(request, pid, Article.pdf.id, type=Article,
                              repo=repo, headers=extra_headers)
    except RequestFailed:
        raise Http404


# permission ? 
def view_datastream(request, pid, dsid):
    'Access raw object datastreams'
    # initialize local repo with logged-in user credentials & call generic view
    return raw_datastream(request, pid, dsid, type=Article, repo=Repository(request=request))


def recent_uploads(request):
    'View recent uploads to the system.'
    solr = solr_interface()
    solrquery = solr.query(content_model=Article.ARTICLE_CONTENT_MODEL).sort_by('-last_modified')
    results = solrquery.execute()
    return render(request, 'publication/recent.html', {'recent_uploads': results})
