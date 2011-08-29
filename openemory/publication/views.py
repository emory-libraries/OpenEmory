from django.conf import settings
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import render
from django.template.context import RequestContext
from django.template.loader import get_template
from django.utils.safestring import mark_safe
from eulcommon.djangoextras.http import HttpResponseSeeOtherRedirect
from eulfedora.server import Repository
from eulfedora.util import RequestFailed
from eulfedora.views import raw_datastream
from sunburnt import sunburnt

from openemory.accounts.auth import login_required
from openemory.publication.forms import UploadForm, DublinCoreEditForm
from openemory.publication.models import Article
from openemory.util import md5sum


@login_required
def upload(request):
    '''Upload a file and ingest an
    :class:`~openemory.publication.models.Article` object into the
    repository.  On GET, displays the upload form.  On POST with a
    valid file, ingests the content into Fedora.
    '''
    context = {}
    if request.method == 'POST':
        form = UploadForm(request.POST, request.FILES)
        if form.is_valid():
            # init repo with request to use logged-in user credentials for fedora access
            repo = Repository(request=request) 
            obj = repo.get_object(type=Article)
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
                    return HttpResponseSeeOtherRedirect(reverse('site-index'))
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
        repo = Repository()
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


def recent_uploads(request):
    'View recent uploads to the system.'
    solr = sunburnt.SolrInterface(settings.SOLR_SERVER_URL)
    solrquery = solr.query(content_model=Article.ARTICLE_CONTENT_MODEL).sort_by('-last_modified')
    results = solrquery.execute()
    return render(request, 'publication/recent.html', {'recent_uploads': results})
