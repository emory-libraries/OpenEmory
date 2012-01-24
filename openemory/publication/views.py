from django.conf import settings
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.core.serializers.json import DjangoJSONEncoder
from django.http import Http404, HttpResponse, HttpResponseForbidden, HttpResponseBadRequest
from django.shortcuts import render, get_object_or_404
from django.template.context import RequestContext
from django.template.loader import get_template
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from eulcommon.djangoextras.http import HttpResponseSeeOtherRedirect
from eulcommon.searchutil import search_terms
from eulfedora.models import DigitalObjectSaveFailure
from eulfedora.server import Repository
from eulfedora.util import RequestFailed, PermissionDenied
from eulfedora.views import raw_datastream
import json
from sunburnt import sunburnt
from urllib import urlencode

from openemory.accounts.auth import login_required, permission_required
from openemory.harvest.models import HarvestRecord
from openemory.publication.forms import UploadForm, \
        BasicSearchForm, ArticleModsEditForm
from openemory.publication.models import Article, AuthorName
from openemory.util import md5sum, solr_interface, paginate

# solr fields we usually want for views that list articles
ARTICLE_VIEW_FIELDS = [ 'pid', 'state',
    'created', 'dsids', 'last_modified', 'owner', 'pmcid', 'title',
    'parsed_author',]

json_serializer = DjangoJSONEncoder(ensure_ascii=False, indent=2)

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
            # check that user has required permissions
            if not request.user.has_perm('harvest.ingest_harvestrecord'):
                return HttpResponseForbidden('Permission Denied',
                                             mimetype='text/plain')

            if 'pmcid' not in request.POST or not request.POST['pmcid']:
                return HttpResponseBadRequest('No record specified for ingest',
                                              mimetype='text/plain')
            record = get_object_or_404(HarvestRecord, pmcid=request.POST['pmcid'])
            # NOTE: possible race condition. see:
            #   http://www.no-ack.org/2010/07/mysql-transactions-and-django.html
            #   https://coderanger.net/2011/01/select-for-update/
            #   https://code.djangoproject.com/ticket/2705
            # due to the low likelihood of this happening in production and
            # the small impact if it does, ignoring it until the above
            # django ticket #2705 is released and its select_for_update()
            # syntax is available.
            if not record.ingestable:
                return HttpResponseBadRequest('Record cannot be ingested',
                                              mimetype='text/plain')
            record.mark_in_process()

            try:
                # initialize a new article object from the harvest record
                obj = record.as_publication_article(repo=repo)
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
                record.status = record.DEFAULT_STATUS
                record.save()
                return HttpResponse('Error: %s' % rf,
                                    mimetype='text/plain', status=500)
                
        # otherwise, assume form data was POSTed and handle as upload form
        else:
            form = UploadForm(request.POST, request.FILES)
            if form.is_valid():
                obj = repo.get_object(type=Article)
                # TODO: move init logic into an Article class method?
                # TODO: remove initial dc field? set preliminary mods title from file?
                uploaded_file = request.FILES['pdf']
                # use filename as preliminary title
                obj.label = uploaded_file.name
                # copy object label into dc:title
                obj.dc.content.title = obj.label
                # set the username of the currently-logged in user as object owner
                obj.owner = request.user.username
                # ingest as inactive (not publicly visible until author edits & publishes)
                obj.state = 'I' 
                # set uploaded file as pdf datastream content
                obj.pdf.content = uploaded_file
                # for now, use the content type passed by the browser (even though we know it is unreliable)
                # eventually, we'll want to use mime magic to inspect files before ingest
                obj.pdf.mimetype = uploaded_file.content_type 
                obj.dc.content.format = obj.pdf.mimetype

                # set static MODS values that will be the same for all uploaded articles
                obj.descMetadata.content.resource_type = 'text'
                obj.descMetadata.content.genre = 'Article'
                obj.descMetadata.content.create_physical_description()
                obj.descMetadata.content.physical_description.media_type = 'application/pdf'

                # set current user as first author
                obj.descMetadata.content.authors.append(AuthorName(id=request.user.username,
                                                                   family_name=request.user.last_name,
                                                                   given_name=request.user.first_name,
                                                                   affiliation='Emory University'))
                
                # calculate MD5 checksum for the uploaded file before ingest
                obj.pdf.checksum = md5sum(uploaded_file.temporary_file_path())
                obj.pdf.checksum_type = 'MD5'
                try:
                    saved = obj.save('upload via OpenEmory')
                    if saved:
                        messages.success(request,
                            'Successfully uploaded PDF <%(tag)s>%(file)s</%(tag)s>. Please enter article information.' 
                                 % {'file': uploaded_file.name, 'pid': obj.pid, 'tag': 'strong'})
                        next_url = reverse('publication:edit',
                                           kwargs={'pid': obj.pid})
                        return HttpResponseSeeOtherRedirect(next_url)
                except RequestFailed as rf:
                    context['error'] = rf
            
    else:
        # init unbound form for display
        form = UploadForm()
        
    context['form'] = form

    return render(request, 'publication/upload.html', context)

def view_article(request, pid):
    """View to display an
    :class:`~openemory.publication.models.Article` .
    """
    # init the object as the appropriate type
    try:
        repo = Repository(request=request)
        obj = repo.get_object(pid=pid, type=Article)
        # TODO: if object is not published (i.e. status != 'A'),
        # should probably only display to authors/admins
        if not obj.exists:
            raise Http404
    except RequestFailed:
        raise Http404

    return render(request, 'publication/view.html', {'article': obj})



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

    if request.user.username != obj.owner  and \
           not request.user.has_perm('publication.review_article'):
        # not article author or reviewer - deny
        tpl = get_template('403.html')
        return HttpResponseForbidden(tpl.render(RequestContext(request)))

    # initial form data
    initial_data = {
        'reviewed': bool(obj.provenance.exists and \
                         obj.provenance.content.date_reviewed)
    }

    context = {'obj': obj}

    # on GET, instantiate the form with existing object data (if any)
    if request.method == 'GET':
        form = ArticleModsEditForm(instance=obj.descMetadata.content, initial=initial_data)

    elif request.method == 'POST':
        form = ArticleModsEditForm(request.POST, instance=obj.descMetadata.content)
        if form.is_valid():
            form.update_instance()
            # if user is a reviewer, check if review event needs to be added
            if request.user.has_perm('publication.review_article'):
                # if reviewed is selected, store review event
                if 'reviewed' in form.cleaned_data and form.cleaned_data['reviewed']:
                    # TODO: use short-form ARK when we add them.
                    # initialize minimal premis object info (required for validity)
                    obj.provenance.content.init_object(obj.pid, 'pid')
                    # add the review event
                    if not obj.provenance.content.review_event:
                        obj.provenance.content.reviewed(request.user)
                    
            # TODO: update dc from MODS?
            # also use mods:title as object label
            obj.label = obj.descMetadata.content.title 

            # check if submitted via "save", keep unpublished
            if 'save-record' in request.POST :
                # make sure object state is inactive
                obj.state = 'I'
                msg_action = 'Saved'
                # TODO: save probably shouldn't mark inactive, but just NOT publish
                # and keep inactive if previously unpublished...
            # submitted via "publish"
            elif 'publish-record' in request.POST:
                # make sure object states is active
                obj.state = 'A'
                msg_action = 'Published'
            elif 'review-record' in request.POST :
                # don't change object status when reviewing
                msg_action = 'Reviewed'

            # when saving a published object, calculate the embargo end date
            if obj.state == 'A':
                obj.descMetadata.content.calculate_embargo_end()

            try:
                obj.save('updated metadata')
                # distinguish between save/publish in success message
                messages.success(request, '%s %s' % (msg_action, obj.label))

                # if submitted via 'publish', redirect to article detail view
                if 'publish-record' in request.POST :
                    # redirect to article detail view
                    return HttpResponseSeeOtherRedirect(reverse('publication:view',
                                               kwargs={'pid': obj.pid}))
                # if submitted via 'review', redirect to review list
                if 'review-record' in request.POST :
                    # redirect to article detail view
                    return HttpResponseSeeOtherRedirect(reverse('publication:review-list'))
                
                # otherwise, redisplay the edit form
                
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

        # form was posted but not valid
        else:
            context['invalid_form'] = True

    context['form'] = form
                    
    return render(request, 'publication/edit.html', context,
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
    # restrict to active (published) articles only
    solrquery = solr.query().filter(content_model=Article.ARTICLE_CONTENT_MODEL,
                                    state='A') \
                    .field_limit(ARTICLE_VIEW_FIELDS) \
                    .sort_by('-last_modified')
    
    results, show_pages = paginate(request, solrquery)
    return render(request, 'publication/recent.html', 
                  {'recent_uploads': results, 'show_pages' : show_pages})

def search(request):
    search = BasicSearchForm(request.GET)
    solr = solr_interface()
    q = solr.query().filter(content_model=Article.ARTICLE_CONTENT_MODEL,
                            state='A') # restrict to active (published) articles only
    terms = []
    if search.is_valid():
        if search.cleaned_data['keyword']:
            keyword = search.cleaned_data['keyword']
            terms = search_terms(keyword)
            q = q.query(*terms)

    highlight_fields = [ 'abstract', 'fulltext', ]
    # common query options
    q = q.highlight(highlight_fields).sort_by('-score')

    # for the paginated version, limit to display fields + score
    results, show_pages = paginate(request,
                                   q.field_limit(ARTICLE_VIEW_FIELDS, score=True))

    return render(request, 'publication/search-results.html', {
            'results': results,
            'search_terms': terms,
            'show_pages': show_pages,
            'url_params': urlencode({'keyword': search.cleaned_data['keyword']})
        })


def suggest(request, field):
    '''Suggest terms based on a specified field and term prefix, using
    Solr facets.  Returns a JSON response with the 15 most common
    matching terms in the requested field with the specified prefix.

    .. Note::

        Due to the current implementation and the limitations of facet
        querying in Solr, the search term is case-sensitive and only
        matches at the beginning of the string.
    
    Return format is suitable for use with `JQuery UI Autocomplete`_
    widget.

    .. _JQuery UI Autocomplete: http://jqueryui.com/demos/autocomplete/

    :param request: the http request passed to the original view
        method (used to retrieve the search term)
            
    :param field: the name of the field to query in Solr (without the
        *_facet* portion).  Currently supported fields: **funder**,
        **journal_title**, **journal_publisher**, **keyword**,
        **author_affiliation**
    '''
    
    term = request.GET.get('term', '')
    solr = solr_interface()
    # generate solr facet field name
    facet_field = '%s_facet' % field
    # query all documents but don't actually return any of them
    facetq = solr.query().paginate(rows=0)
    # return the 15 most common terms in the requested facet field
    # with a specified prefix
    facetq = facetq.facet_by(facet_field, prefix=term,
                                       sort='count',
                                       limit=15)
    facets = facetq.execute().facet_counts.facet_fields
    
    # generate a dictionary to return via json with label (facet value
    # + count), and actual value to use
    suggestions = [{'label': '%s (%d)' % (facet, count),
                    'value': facet}
                   for facet, count in facets[facet_field]
                   ]
    return  HttpResponse(json_serializer.encode(suggestions),
                         mimetype='application/json')


@permission_required('publication.review_article') 
def review_queue(request):
    '''List published but unreviewed articles so admins can review
    metadata.
    '''
    solr = solr_interface()
    q = solr.query().exclude(review_date__any=True)\
        	.filter(content_model=Article.ARTICLE_CONTENT_MODEL,
                        state='A') # restrict to active (published) articles only
    q = q.sort_by('created').field_limit(ARTICLE_VIEW_FIELDS)
    results, show_pages = paginate(request, q)

    return render(request, 'publication/review-queue.html', {
        'results': results, 'show_pages': show_pages,
        })

