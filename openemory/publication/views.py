import datetime
import json
import logging
from urllib import urlencode
from rdflib import URIRef, Literal

from django.conf import settings
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.core.serializers.json import DjangoJSONEncoder
from django.core.mail import mail_managers
from django.db.models import Sum
from django.http import Http404, HttpResponse, HttpResponseForbidden, \
    HttpResponseBadRequest, HttpResponsePermanentRedirect
from django.shortcuts import render, get_object_or_404, redirect
from django.template.context import RequestContext
from django.template.loader import get_template, render_to_string
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_http_methods, last_modified
from django.views.decorators.csrf import csrf_exempt
from eulcommon.djangoextras.http import HttpResponseSeeOtherRedirect
from eulcommon.searchutil import search_terms
from eulfedora.models import DigitalObjectSaveFailure
from eulfedora.rdfns import relsext, oai
from eulfedora.server import Repository
from eulfedora.util import RequestFailed, PermissionDenied
from eulfedora.views import raw_datastream, raw_audit_trail
from pyPdf.utils import PdfReadError
from sunburnt import sunburnt

from openemory.accounts.auth import login_required, permission_required
from openemory.common import romeo
from openemory.harvest.models import HarvestRecord
from openemory.publication.forms import UploadForm, AdminUploadForm, \
        BasicSearchForm, SearchWithinForm, ArticleModsEditForm, OpenAccessProposalForm
from openemory.publication.models import Article, AuthorName, ArticleStatistics, \
	ResearchFields, FeaturedArticle
from openemory.util import md5sum, solr_interface, paginate

logger = logging.getLogger(__name__)


# solr fields we usually want for views that list articles
ARTICLE_VIEW_FIELDS = ['id', 'pid', 'state',
    'created', 'dsids', 'last_modified', 'owner', 'pmcid', 'title',
    'parsed_author','embargo_end', 'abstract', 'researchfield',
    'journal_title', 'pubyear', 'withdrawn']

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

        # Collection to which all articles will belong for use with OAI
        coll =  repo.get_object(pid=settings.PID_ALIASES['oe-collection'])

        # ajax request: should pass pmcid for HarvestRecord to be ingested
        if request.is_ajax():
            # check that user has required permissions
            if not request.user.has_perm('harvest.ingest_harvestrecord'):
                return HttpResponseForbidden('Permission Denied',
                                             mimetype='text/plain')

            # TODO: when more external systems are added in addition
            # to Pub Meb, we will have to figure out how to identify
            # which system is being referenced.  Will likely have to
            # add to the Harvest record model.

            # TODO: Update so premis events are included on object
            # ingest, rather than requiring a secondary save?
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

                # Add to OpenEmory Collection
                obj.collection = coll

                saved = obj.save('Ingest from harvested record PubMed Central %d' % \
                                 record.pmcid)
                if saved:
                    # mark the database record as ingested
                    record.mark_ingested()

                    #add harvested premis event
                    obj.provenance.content.init_object(obj.pid, 'pid')
                    if not obj.provenance.content.harvest_event:
                        obj.provenance.content.harvested(request.user, record.pmcid)
                        obj.save('added harvested event')

                    # return a 201 Created with new location
                    response = HttpResponse('Ingested as %s' % obj.pid,
                                            mimetype='text/plain',
                                            status=201)
                    # return a location for the newly created object
                    response['Location'] = reverse('publication:view',
                                                   kwargs={'pid': obj.pid})
                    return response
            except RequestFailed as rf:
                record.status = record.DEFAULT_STATUS
                record.save()
                return HttpResponse('Error: %s' % rf,
                                    mimetype='text/plain', status=500)

        # otherwise, assume form data was POSTed and handle as upload form
        else:
            # admins (people who can "review_article") have the option of
            # uploading their own articles or those of others. this admin
            # form requires them to select which role they are performing so
            # that we can properly reflect the legal statements they agree
            # to in fedora.
            if request.user.has_perm('publication.review_article'):
                form = AdminUploadForm(request.POST, request.FILES)
            else:
                form = UploadForm(request.POST, request.FILES)

            if form.is_valid():
                # LEGAL NOTE: Failure to assent (in
                # form.cleaned_data['assent']) is currently processed as an
                # invalid form. Legal counsel recommends requiring such
                # assent before processing file upload.
                assert form.cleaned_data.get('assent', False)

                obj = repo.get_object(type=Article)

                # a few metadata values depend on whether the user submitted
                # as an author or mediated submission.
                statement = form.cleaned_data.get('legal_statement', 'AUTHOR')

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
                if statement == 'AUTHOR':
                    obj.descMetadata.content.authors.append(AuthorName(id=request.user.username,
                                                                    family_name=request.user.last_name,
                                                                    given_name=request.user.first_name,
                                                                    affiliation='Emory University'))

                # calculate MD5 checksum for the uploaded file before ingest
                obj.pdf.checksum = md5sum(uploaded_file.temporary_file_path())
                obj.pdf.checksum_type = 'MD5'

                # Add to OpenEmory Collection
                obj.collection = coll

                try:
                    saved = obj.save('upload via OpenEmory')
                    if saved:
                        messages.success(request,
                            'Success! Your article was uploaded. Please complete the required fields in Citation Information and submit.',
                            extra_tags='upload')
                        next_url = reverse('publication:edit',
                                           kwargs={'pid': obj.pid})

                        #add uploaded premis event
                        obj.provenance.content.init_object(obj.pid, 'pid')

                        if not obj.provenance.content.upload_event:
                            # LEGAL NOTE: Legal counsel recommends what we
                            # require assent to deposit before processing
                            # file upload. We do this by making the assent
                            # field required in the form. Thus assent here
                            # should always be True. We're leaving this
                            # check in place in case current or future code
                            # error accidentally changes that precondition.
                            #
                            # For the statement that the user agreed to, we
                            # check the form. The admin form has a required
                            # legal_statement that specifies this. The
                            # regular admin form has no such field: It only
                            # presents the author option.
                            assent = form.cleaned_data.get('assent', False)
                            statement = (form.cleaned_data.get('legal_statement', 'AUTHOR')
                                         if assent else None)

                            obj.provenance.content.uploaded(request.user,
                                    legal_statement=statement)
                            obj.save('added upload event')

                        return HttpResponseSeeOtherRedirect(next_url)
                except RequestFailed as rf:
                    context['error'] = rf

    else:
        # init unbound form for display
        if request.user.has_perm('publication.review_article'):
            form = AdminUploadForm({'legal_statement': 'MEDIATED'})
        else:
            form = UploadForm()

    context['form'] = form

    return render(request, 'publication/upload.html', context)


def object_last_modified(request, pid):
    '''Return the last modification date for an object in Fedora, to
    allow for conditional processing with use with
    :meth:`django.views.decorators.last_modified`.'''
    # TODO: does this make sense to put in eulfedora?
    try:
        repo = Repository(request=request)
        return repo.get_object(pid=pid).modified
    except RequestFailed:
        pass

# TODO: consider renaming to get_article_or_404 for consistency with django
def _get_article_for_request(request, pid):
    try:
        repo = Repository(request=request)
        obj = repo.get_object(pid=pid, type=Article)

        # TODO: if object is not published (i.e. status != 'A'),
        # should probably only display to authors/admins
        if not obj.exists:
            raise Http404
    except RequestFailed:
        raise Http404
    return obj


def _parse_name(terms):
    '''
    parse the terms to see if it looks like a name

    works with:
    first last
    first mi last
    last, first
    last, first mi

    :param terms: a the keyword search terms

    returns: a dict with:
    full_name (firstname lastname),
    first_name,
    last_name,
    last_first(lastname, firstname)
    '''

    fname = ''
    lname = ''
    mi = ''
    name_info = {}
    if(len(terms) == 1):
        name_parts = terms[0].split(' ')
        if len(name_parts) == 2:
            if name_parts[0].endswith(','):
                fname = name_parts[1]
                lname = name_parts[0][:-1]
            else:
                fname = name_parts[0]
                lname = name_parts[1]
            name_info['full_name'] = "%s %s" % (fname, lname)
            name_info['first_name'] = fname
            name_info['last_name'] = lname
            name_info['last_first'] = "%s, %s" % (lname, fname)
        elif len(name_parts) == 3:
            if name_parts[0].endswith(','):
                fname = name_parts[1]
                lname = name_parts[0][:-1]
                mi = name_parts[2]
            else:
                fname = name_parts[0]
                lname = name_parts[2]
                mi =name_parts[1]
            name_info['full_name'] = "%s %s %s" % (fname, mi, lname)
            #when there is a middle initial it is included in first name
            name_info['first_name'] = '%s %s' % (fname, mi)
            name_info['last_name'] = lname
            name_info['last_first'] = "%s, %s %s" % (lname, fname, mi)
    return name_info


# FIXME: this needs a vary header (varies if user is logged in - session? cookie?)
@last_modified(object_last_modified)
def view_article(request, pid):
    """View to display an
    :class:`~openemory.publication.models.Article` .
    """
    repo = Repository(request=request)
    obj = repo.get_object(pid=pid, type=Article)

    # *** SPECIAL CASE (should be semi-temporary)
    # (Added 12/2012; can be removed once openemory:* pids are no longer
    # indexed, possibly after a few months.)
    # Early objects were ingested with the wrong pidspace. If someone
    # tries to access an openemory:### pid and the corresponding
    # pid exists in the default pidspace, permanent redirect to the
    # existing object.  Otherwise, 404 as usual.
    if obj.pidspace == 'openemory':
        realpid = pid.replace('openemory', settings.FEDORA_PIDSPACE)
        obj = repo.get_object(pid=realpid, type=Article)
        if obj.exists:
            return HttpResponsePermanentRedirect(reverse('publication:view',
                kwargs={'pid': realpid}))

    obj = _get_article_for_request(request, pid)

    # only increment stats on GET requests (i.e., not on HEAD)
    if request.method == 'GET':
        stats = obj.statistics()
        stats.num_views += 1
        stats.save()

    return render(request, 'publication/view.html', {'article': obj})


@login_required
def edit_metadata(request, pid):
    """View to edit the metadata for an existing
    :class:`~openemory.publication.models.Article` .

    On GET, display the form.  When valid form data is POSTed, updates
    thes object.
    """
    # response status should be 200 unless something goes wrong
    status_code = 200
    obj = _get_article_for_request(request, pid)

    if request.user.username not in obj.owner  and \
           not request.user.has_perm('publication.review_article'):
        # not article author or reviewer - deny
        tpl = get_template('403.html')
        return HttpResponseForbidden(tpl.render(RequestContext(request)))

    # initial form data
    initial_data = {
        'reviewed': bool(obj.provenance.exists and \
                         obj.provenance.content.date_reviewed),
        'featured' : FeaturedArticle.objects.filter(pid=obj.pid)
    }

    context = {'article': obj}

    # see if current user is in the Site Admin Group
    is_admin = 'Site Admin' in  [g.name for g in request.user.groups.all()]

    # on GET, instantiate the form with existing object data (if any)
    if request.method == 'GET':
        form = ArticleModsEditForm(instance=obj.descMetadata.content,
                                   initial=initial_data, make_optional=False, pid=obj.pid)

    elif request.method == 'POST':

        #set obj_pid for use with featured article if user has perms to update
        # and the article is published
        if request.user.has_perm('publication.review_article') and obj.state == 'A':
            obj_pid = obj.pid
        else:
            obj_pid = None

        # save a draft
        if 'save-record' in request.POST:
            form = ArticleModsEditForm(request.POST, files=request.FILES,
                                       instance=obj.descMetadata.content, make_optional=True, pid=obj_pid)
        # publish
        else:
            form = ArticleModsEditForm(request.POST, files=request.FILES,
                                       instance=obj.descMetadata.content, make_optional=False, pid=obj_pid, is_admin=is_admin)
        if form.is_valid():
            withdrawn = obj.is_withdrawn
            newly_reinstated = newly_withdrawn = False
            form.update_instance()

            if 'author_agreement' in request.FILES:
                new_agreement = request.FILES['author_agreement']
                obj.authorAgreement.content = new_agreement
                obj.authorAgreement.mimetype = new_agreement.content_type

            # The pid of the Article only set if user has review perms
            # This is used to indicate if the featured flag should be updated or not
            obj_pid = None

            # if user is a reviewer, check if review/withdraw event needs to be added
            if request.user.has_perm('publication.review_article'):
                # if reviewed is selected, store review event
                if 'reviewed' in form.cleaned_data and form.cleaned_data['reviewed']:
                    # TODO: use short-form ARK when we add them.
                    # initialize minimal premis object info (required for validity)
                    obj.provenance.content.init_object(obj.pid, 'pid')
                    # add the review event
                    if not obj.provenance.content.review_event:
                        obj.provenance.content.reviewed(request.user)

                # if withdrawal/reinstatement state on the form doesn't
                # match the object, update the object
                if withdrawn:
                    if 'reinstate' in form.cleaned_data \
                            and form.cleaned_data['reinstate']:
                        obj.provenance.content.init_object(obj.pid, 'pid')
                        obj.provenance.content.reinstated(request.user,
                                form.cleaned_data['reinstate_reason'])
                        withdrawn = False
                        newly_reinstated = True
                else:
                    if 'withdraw' in form.cleaned_data \
                            and form.cleaned_data['withdraw']:
                        obj.provenance.content.init_object(obj.pid, 'pid')
                        obj.provenance.content.withdrawn(request.user,
                                form.cleaned_data['withdraw_reason'])
                        withdrawn = True
                        newly_withdrawn = True

            # TODO: update dc from MODS?
            # also use mods:title as object label
            obj.label = obj.descMetadata.content.title

            # FIXME: incorrect interactions between withdrawal state and
            # save/pub/rev state

            # update object state:
            # withdrawn objects always get inactive state
            if withdrawn:
                obj.state = 'I'
            # check if submitted via "save", keep unpublished
            elif 'save-record' in request.POST :
                obj.state = 'I'
                # TODO: save probably shouldn't mark inactive, but just NOT publish
                # and keep inactive if previously unpublished...
            # submitted via "publish"
            elif 'publish-record' in request.POST:
                # make sure object states is active
                obj.state = 'A'

            # get result message text:
            # check if submitted via "save", keep unpublished
            if 'save-record' in request.POST :
                msg_action = 'saved'
            # submitted via "publish"
            elif 'publish-record' in request.POST:
                msg_action = 'published'
            elif 'review-record' in request.POST :
                msg_action = 'reviewed'

            if newly_withdrawn:
                msg_action = 'withdrawn'
            elif newly_reinstated:
                msg_action = 'reinstated and ' + msg_action

            msg_action = msg_action[0].upper() + msg_action[1:]

            # when saving a published object, calculate the embargo end date and add OAI info
            if obj.is_published:
                obj.descMetadata.content.calculate_embargo_end()
                obj.oai_itemID = "oai:ark:/25593/%s" % obj.noid

            try:
                obj.save('updated metadata')
                # distinguish between save/publish in success message
                messages.success(request, '%(msg)s <%(tag)s>%(label)s</%(tag)s>' % \
                                 {'msg': msg_action, 'label': obj.label, 'tag': 'strong'})

                # if submitted via 'publish' or 'save', redirect to article detail view
                if 'publish-record' in request.POST  or 'save-record' in request.POST:
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
    # research fields/subjects for jquery category-autocomplete
    context['subject_data'] = json_serializer.encode(ResearchFields().as_category_completion())

    return render(request, 'publication/edit.html', context,
                  status=status_code)


def download_pdf(request, pid):
    '''View to allow access the PDF datastream of a
    :class:`openemory.publication.models.Article` object.  Sets a
    content-disposition header that will prompt the file to be saved
    with a default title based on the object label.

    Returns the original Article PDF with a cover page, if possible;
    if there is an error generating the cover page version of the PDF,
    the original PDF will be returned.
    '''
    repo = Repository(request=request)
    try:
        # retrieve the object so we can use it to set the download filename
        obj = repo.get_object(pid, type=Article)
        extra_headers = {
            # generate a default filename based on the object
            # FIXME: what do we actually want here? ARK noid?
            'Content-Disposition': "attachment; filename=%s.pdf" % obj.pid,
            #'Last-Modified': obj.pdf.created,
        }
        # if the PDF is embargoed, check that user should have access (bail out if not)
        if obj.is_embargoed:
            # only logged-in authors or site admins are allowed
            if not request.user.is_authenticated():
                tpl = get_template('401.html')
                return HttpResponse(tpl.render(RequestContext(request)), status=401)
            if not (request.user.username in obj.owner \
                   or request.user.has_perm('publication.view_embargoed')):
                tpl = get_template('403.html')
                return HttpResponseForbidden(tpl.render(RequestContext(request)))

        # at this point we know that we're authorized to view the pdf. bump
        # stats before doing the deed (but only if this is a GET)
        if request.method == 'GET':
            stats = obj.statistics()
            stats.num_downloads += 1
            stats.save()

        try:
            content = obj.pdf_with_cover()
            response = HttpResponse(content, mimetype='application/pdf')
            # pdf+cover depends on metadata; if descMetadata changed more recently
            # than pdf, use the metadata last-modified date.
            #if obj.descMetadata.created > obj.pdf.created:
            #    extra_headers['Last-Modified'] = obj.descMetadata.created
            # NOTE: could also potentially change based on cover logic changes...

            # FIXME: any way to calculate content-length? ETag based on pdf+mods ?
            for key, val in extra_headers.iteritems():
                response[key] = val
            return response

        except RequestFailed:
            # re-raise so we can handle it below. TODO: simplify this logic a bit
            raise
        except:
            logger.warn('Exception on %s; returning without cover page' % obj.pid)
            # cover page failed - fall back to pdf without
            # use generic raw datastream view from eulfedora
            return raw_datastream(request, pid, Article.pdf.id, type=Article,
                                  repo=repo, headers=extra_headers)

    except RequestFailed:
        raise Http404


# permission ?
def view_datastream(request, pid, dsid):
    '''Access object datastreams on
    :class:`openemory.publication.model.Article` objects'''
    # initialize local repo with logged-in user credentials & call generic view
    return raw_datastream(request, pid, dsid, type=Article, repo=Repository(request=request))

def view_private_datastream(request, pid, dsid):
    '''Access raw object datastreams accessible only to object owners and
    superusers.'''
    # FIXME: refactor out shared code between this and download_pdf and
    # possibly view_datastream
    repo = Repository(request=request)
    try:
        # retrieve the object so we can use it to set the download filename
        obj = repo.get_object(pid, type=Article)
        extra_headers = {
            # generate a default filename based on the object
            # FIXME: what do we actually want here? ARK noid?
            'Content-Disposition': "attachment; filename=%s-%s.pdf" %
                    (obj.pid, dsid),
        }
        # use generic raw datastream view from eulfedora
        if (request.user.is_authenticated()) and \
           (request.user.username in obj.owner
               or request.user.is_superuser):
            return raw_datastream(request, pid, dsid, type=Article,
                                  repo=repo, headers=extra_headers)
        elif request.user.is_authenticated():
            tpl = get_template('403.html')
            return HttpResponseForbidden(tpl.render(RequestContext(request)))
        else:
            tpl = get_template('401.html')
            return HttpResponse(tpl.render(RequestContext(request)), status=401)
    except RequestFailed:
        raise Http404

@permission_required('publication.view_admin_metadata')
def audit_trail(request, pid):
    '''Access XML audit trail on
    	:class:`openemory.publication.model.Article` objects'''
    return raw_audit_trail(request, pid, type=Article,
                           repo=Repository(request=request))


def bibliographic_metadata(request, pid):
    '''Return bibliographic metadata for an article. Currently this view is
    used primarily to support import to EndNote, though it may be extended
    to support other formats in the future.'''

    article = _get_article_for_request(request, pid)
    return _article_as_ris(article, request)

def _article_as_ris(obj, request):
    '''Serialize article bibliographic metadata in RIS (Research Info
    Systems--essentially EndNote) format.

    :param obj: an :class:`~openemory.publication.models.Article`
    :param request: an :class:`~django.http.HttpRequest` to help absolutize
                    the article URL, if available
    :returns: an :class:`~django.http.HttpResponse`
    '''
    # The spec talks about the general structure of an RIS file:
    #   http://www.adeptscience.co.uk/kb/article/FE26
    # Its list of tags is woefully incomplete, though: It never defines
    # title, though it does use TI in an example for something that looks
    # sorta like a title. Using the wikipedia tag list for now:
    #   http://en.wikipedia.org/w/index.php?title=RIS_(file_format)&oldid=461366552

    # NOTE: We're being explicit about using utf-8 here, so be precise about
    # it. Construct all strings as unicode objects, and convert to utf-8 at
    # the end.
    mods = obj.descMetadata.content

    header_lines = []
    header_lines.append(u'Provider: Emory University Libraries')
    header_lines.append(u'Database: OpenEmory')
    header_lines.append(u'Content: text/plain; charset="utf-8"')

    reference_lines = []
    reference_lines.append(u'TY  - JOUR')
    if mods.title_info:
        if mods.title_info.title:
            reference_lines.append(u'TI  - ' + mods.title_info.title)
        if mods.title_info.subtitle:
            reference_lines.append(u'T2  - ' + mods.title_info.subtitle)
    for author in mods.authors:
        reference_lines.append(u'AU  - %s, %s' % (author.family_name, author.given_name))
    if mods.journal:
        if mods.journal.title:
            reference_lines.append(u'JO  - ' + mods.journal.title)
        if mods.journal.publisher:
            reference_lines.append(u'PB  - ' + mods.journal.publisher)
        if mods.journal.volume:
            reference_lines.append(u'VL  - ' + mods.journal.volume.number)
        if mods.journal.number:
            reference_lines.append(u'IS  - ' + mods.journal.number.number)
        if mods.journal.pages:
            if mods.journal.pages.start:
                reference_lines.append(u'SP  - ' + mods.journal.pages.start)
            if mods.journal.pages.end:
                reference_lines.append(u'EP  - ' + mods.journal.pages.end)
    if mods.publication_date:
        reference_lines.append(u'PY  - ' + mods.publication_date[:4])
        reference_lines.append(u'DA  - ' + mods.publication_date[:10])
    for keyword in mods.keywords:
        value = _mods_kw_as_ris_value(keyword)
        if value is not None:  # it's possible this could be empty (separate bug?)
            reference_lines.append(u'KW  - ' + value)
    if mods.final_version and mods.final_version.doi:
        reference_lines.append(u'DO  - ' + mods.final_version.doi)
    if mods.language:
        reference_lines.append(u'LA  - ' + mods.language)
    reference_lines.append(u'UR  - ' + request.build_absolute_uri(obj.get_absolute_url()))
    reference_lines.append(u'ER  - ')

    header_data = u''.join(line + u'\r\n' for line in header_lines)
    reference_data = u''.join(line + u'\r\n' for line in reference_lines)
    response_data = u'%s\r\n%s' % (header_data, reference_data)

    return HttpResponse(response_data.encode('utf-8'), mimetype='application/x-research-info-systems')


def _mods_kw_as_ris_value(kw):
    '''Serialize a :class:`~openemory.publication.mods.Keyword` for
    inclusion in an RIS file (e.g., in :func:`_article_as_ris`).'''
    # FIXME: does this really belong here?
    # TODO: generalize as a utility method on local mods.keyword

    if kw.geographic:
        return kw.geographic
    if kw.topic:
        return kw.topic
    if kw.title:
        return kw.title
    if kw.name:
        return unicode(kw.name)


def site_index(request):
    '''Site index page, including 10 most viewed and 10 recently
    published articles.'''
    solr = solr_interface()
    # FIXME: this is very similar logic to summary view
    # (should be consolidated)

    # common query options for both searches
    q = solr.query().filter(content_model=Article.ARTICLE_CONTENT_MODEL,
                            state='A') \
                            .field_limit(ARTICLE_VIEW_FIELDS)

    # find most viewed content
    # - get distinct list of pids (no matter what year), and aggregate views
    # - make sure article has at least 1 download to be listed
    stats = ArticleStatistics.objects.values('pid').distinct() \
               .annotate(all_views=Sum('num_views'), all_downloads=Sum('num_downloads')) \
               .filter(all_views__gt=0) \
               .order_by('-all_views') \
               .values('pid', 'all_views', 'all_downloads')[:10]
    # list of pids in most-viewed order
    pids = [st['pid'] for st in stats]
    if pids:
        # build a Solr OR query to retrieve browse details on most viewed records
        pid_filter = solr.Q()
        for pid in pids:
            pid_filter |= solr.Q(pid=pid)
        most_viewed = q.filter(pid_filter).execute()
        # re-sort the solr results according to stats order
        most_viewed = sorted(most_viewed, cmp=lambda x,y: cmp(pids.index(x['pid']),
                                                              pids.index(y['pid'])))
    else:
        most_viewed = []

    # find ten most recently modified articles that are published on the site
    # FIXME: this logic is not quite right
    # (does not account for review/edit after initial publication)
    recent = q.sort_by('-last_modified').paginate(rows=10).execute()

    # patch download & view counts into solr results
    for item in recent:
        pid = item['pid']
        if pid in pids:
            pidstats = stats[pids.index(pid)]
            item['views'] = pidstats['all_views']
            item['downloads'] = pidstats['all_downloads']
        else:
            item['views'] = item['downloads'] = 0

    # patch download & view counts into solr result
    for item in most_viewed:
        pid = item['pid']
        pidstats = stats[pids.index(pid)]
        item['views'] = pidstats['all_views']
        item['downloads'] = pidstats['all_downloads']

    #Featured Article
    featured_article_pids = FeaturedArticle.objects.order_by('?') # random sort
    if featured_article_pids:
        featured_article_pid = featured_article_pids[0].pid
        solr = solr_interface()
        featured_article = solr.query(pid=featured_article_pid, state='A').\
        field_limit(['pid', 'title']).execute()[0]

    else:
        featured_article = None

    return render(request, 'publication/site_index.html',
                  {'recent_uploads': recent, 'most_viewed': most_viewed, 'featured': featured_article})

def summary(request):
    '''Publication summary page with a list of most downloaded and
    most recent content.'''
    solr = solr_interface()
    # common query options for both searches
    q = solr.query().filter(content_model=Article.ARTICLE_CONTENT_MODEL,
                            state='A') \
                            .field_limit(ARTICLE_VIEW_FIELDS)

    # find ten most recently modified articles that are published on the site
    # FIXME: this logic is not quite right
    # (does not account for review/edit after initial publication)
    recent = q.sort_by('-last_modified').paginate(rows=10).execute()

    # find most downloaded content
    # - get distinct list of pids (no matter what year), and aggregate downloads
    # - make sure article has at least 1 download to be listed
    stats = ArticleStatistics.objects.values('pid').distinct() \
               .annotate(all_downloads=Sum('num_downloads')) \
               .filter(all_downloads__gt=0) \
               .order_by('-all_downloads') \
               .values('pid', 'all_downloads')[:10]

    # FIXME: we should probably explicitly exclude embargoed documents
    # from a "top downloads" list...

    # if we don't have any stats in the system yet, just return an empty list
    if not stats:
        most_dl = []

    # otherwise, use stats results to get article info from solr
    else:
        # list of pids in most-viewed order
        pids = [st['pid'] for st in stats]
        # build a Solr OR query to retrieve browse details on most viewed records
        pid_filter = solr.Q()
        for pid in pids:
            pid_filter |= solr.Q(pid=pid)
        most_dl = q.filter(pid_filter).execute()
        # re-sort the solr results according to stats order
        most_dl = sorted(most_dl, cmp=lambda x,y: cmp(pids.index(x['pid']),
                                                              pids.index(y['pid'])))
    return render(request, 'publication/summary.html',
                  {'most_downloaded': most_dl, 'newest': recent})


def departments(request):
    '''List department names based on article information in solr,
    grouped by division name.'''
    solr = solr_interface()
    r = solr.query(content_model=Article.ARTICLE_CONTENT_MODEL, state='A') \
            .facet_by('division_dept_id', limit=-1, sort='index') \
            .paginate(rows=0) \
            .execute()
    div_depts = r.facet_counts.facet_fields['division_dept_id']

    depts = []
    for d, total in div_depts:
        dept = Article.split_department(d)
        dept['total'] = total
        depts.append(dept)

    return render(request, 'publication/departments.html',
                  {'departments': depts})


def search(request):
    search = BasicSearchForm(request.GET)
    search_within = SearchWithinForm(request.GET)

    solr = solr_interface()

    # restrict to active (published) articles only
    cm_filter = {'content_model': Article.ARTICLE_CONTENT_MODEL,'state': 'A'}

    item_terms = []
    people_terms = []
    if search.is_valid():
        if search.cleaned_data['keyword']:
            keyword = search.cleaned_data['keyword']
            item_terms.extend(search_terms(keyword))
            people_terms.extend(search_terms(keyword))

    #add additional filtering keyword terms from within search
    within_filter = None
    if search_within.is_valid():
        if search_within.cleaned_data['within_keyword']:
            within_keyword = search_within.cleaned_data['within_keyword']
            past_within_keyword = search_within.cleaned_data['past_within_keyword']
            past_within_keyword = "%s %s" % (past_within_keyword, within_keyword) # combine the filters together
            past_within_keyword = past_within_keyword.strip()
            search_within = SearchWithinForm(initial={'keyword': keyword, 'past_within_keyword' :past_within_keyword})
            within_filter = search_terms(past_within_keyword) # now has the new terms added

    q = solr.query().filter(**cm_filter)
    people_q = solr.query().filter(record_type='accounts_esdperson')
    if item_terms:
        name_info = _parse_name(item_terms)
        # if it looks like a name search search only for that person in author name list
        if name_info:
            q = q.filter(creator=name_info['last_first'])
        else:
            q = solr.query(*item_terms).filter(**cm_filter)
    if within_filter:
        q = q.filter(*within_filter)
        item_terms.extend(within_filter)
    if people_terms:
        # if it looks like a name search search only for that person in dir name
        # fall back to searching first and last name fields
        if name_info:
            people_q = people_q.query(directory_name=name_info['full_name'])
            if len(people_q) == 0:
                people_q = people_q.query(first_name=name_info['first_name'], last_name=name_info['last_name'])
        else:
            people_q = people_q.query(name_text=people_terms)

    # url opts for pagination & basis for removing active filters
    urlopts = request.GET.copy()

    # filter/facet  (display name => solr field)
    field_names = [
        {'queryarg': 'year', 'display': 'Year', 'solr': 'pubyear'},
        {'queryarg': 'author', 'display': 'Author', 'solr': 'creator_facet'},
        {'queryarg': 'subject', 'display': 'Subject', 'solr': 'researchfield_facet'},
        {'queryarg': 'journal', 'display': 'Journal', 'solr': 'journal_title_facet'},
        {'queryarg': 'affiliation', 'display': 'Author affiliation', 'solr': 'affiliations_facet'},
        {'queryarg': 'department', 'display': 'Author department', 'solr': 'department_shortname_facet'},
    ]
    display_filters = []
    active_filters = dict((field['queryarg'], []) for field in field_names)
    # filter the solr search based on any facets in the request
    for field in field_names:
        # For multi-valued fields (author, subject), we could have multiple
        # filters on the same field; treat all facet fields as lists.
        for val in request.GET.getlist(field['queryarg']):
            # filter the current solr query
            q = q.filter(**{field['solr']: val})
            people_q = people_q.filter(**{field['solr']: val})

            # add to list of active filters
            active_filters[field['queryarg']].append(val)

            # also add to list for user display & removal
            # - copy the urlopts and remove the current value
            unfacet_urlopts = urlopts.copy()
            val_list = unfacet_urlopts.getlist(field['queryarg'])
            val_list.remove(val)
            unfacet_urlopts.setlist(field['queryarg'], val_list)
            # - tuple of display value and url to remove this filter
            display_filters.append((val, unfacet_urlopts.urlencode()))

    # Update solr query to return values & counts for configured facet fields
    for field in field_names:
        q = q.facet_by(field['solr'], mincount=1)
        # NOTE: may also want to specify a limit; possibly also higher mincount

    # facets currently are not available through paginated result object;
    #  - to get them, run the query without returning any rows
    facet_result = q.paginate(rows=0).execute()
    facet_fields = facet_result.facet_counts.facet_fields

    # add highlighting & relevance ranking
    highlight_fields = [ 'abstract', 'fulltext', ]
    q = q.highlight(highlight_fields).sort_by('-score')
    # for the paginated version, limit to display fields + score
    results, show_pages = paginate(request,
                                   q.field_limit(ARTICLE_VIEW_FIELDS, score=True))

    facets = {}
    facets = []
    # convert facets for display to user;
    for field in field_names:
        if field['solr'] in facet_fields and facet_fields[field['solr']]:
            show_facets = []
            # skip any display facet values that are already in effect
            for val in facet_fields[field['solr']]:
                if val[0] not in active_filters[field['queryarg']]:
                    show_facets.append(val)

            if show_facets:
                facet = {
                    'display': field['display'],
                    'queryarg': field['queryarg'],
                    'values': show_facets
                }
                facets.append(facet)

    people = people_q.paginate(rows=3).execute()

    return render(request, 'publication/search-results.html', {
            'results': results,
            'authors': people,
            'search_terms': item_terms,
            'show_pages': show_pages,
            #used to compare against the embargo_end date
            'now' :  datetime.datetime.now().strftime("%Y-%m-%d"),
            'url_params': urlopts.urlencode(),
            'facets': facets,
            'active_filters': display_filters,
            'search_within': search_within,
        })


def browse_field(request, field):
    '''Browse a list of values for a specific field, e.g. authors,
    subjects, or journal titles.  Displays a list of values for the
    specified field with a count for the number of articles associated
    with the particular author, subject, or journal, and a link to a
    search for articles with the specified field and value.

    :param field: Expected to be one of **authors**, **subjects**, or
	**journals**

    '''
    solr = solr_interface()
    field_to_facet = {
        'authors':      'creator_sorting',
        'subjects':     'researchfield_sorting',
        'journals':     'journal_title_sorting'
    }
    if field not in field_to_facet.keys():
        raise Http404
    facet = field_to_facet[field]
    # mode used for page display and generating search link
    mode = field.rstrip('s')

    #prefix for alpha sorted browse by
    filter = request.GET['filter'] if 'filter' in request.GET else ''
    q = solr.query().filter(content_model=Article.ARTICLE_CONTENT_MODEL,
                            state='A') \
                    .facet_by(facet, mincount=1, limit=-1, sort='index', prefix=filter.lower())
    result = q.paginate(rows=0).execute()
    facets = result.facet_counts.facet_fields[facet]

    #removes name from field for proper presentation
    facets = [(name.split("|")[1], count) for name, count in facets]
    return render(request, 'publication/browse.html', {
        'mode': mode,
        'facets': facets,
        })

SOLR_SUGGEST_FIELDS = ['author_affiliation', 'funder', 'keyword']
SUGGEST_FUNCTIONS = {} # filled in below

def suggest(request, field):
    if field in SOLR_SUGGEST_FIELDS:
        return suggest_from_solr(request, field)
    elif field in SUGGEST_FUNCTIONS:
        return SUGGEST_FUNCTIONS[field](request, field)
    else:
        raise Http404

def suggest_from_solr(request, field):
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
        *_facet* portion).  Currently supported fields:
        **author_affiliation**, **funder**, **journal_publisher**,
        **keyword**
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

def journal_suggestion_data(journal):
    return {
        'label': '%s (%s)' %
            (journal.title, journal.publisher_romeo or
                            'unknown publisher'),
        'value': journal.title,
        'issn': journal.issn,
        'publisher': journal.publisher_romeo,
    }

def suggest_journal_title(request, field):
    term = request.GET.get('term', '')
    journals = romeo.search_journal_title(term, type='starts') if term else []
    suggestions = [journal_suggestion_data(journal) for journal in journals]
    return HttpResponse(json_serializer.encode(suggestions),
                        mimetype='application/json')
SUGGEST_FUNCTIONS['journal_title'] = suggest_journal_title

def publisher_suggestion_data(publisher):
    return {
        'label': ('%s (%s)' % (publisher.name, publisher.alias))
                 if publisher.alias else
                 publisher.name,
        'value': publisher.name,
        'romeo_id': publisher.id,
        'preprint': {
                'archiving': publisher.preprint_archiving,
                'restrictions': [unicode(r)
                                 for r in publisher.preprint_restrictions],
            },
        'postprint': {
                'archiving': publisher.postprint_archiving,
                'restrictions': [unicode(r)
                                 for r in publisher.postprint_restrictions],
            },
        'pdf': {
                'archiving': publisher.pdf_archiving,
                'restrictions': [unicode(r)
                                 for r in publisher.pdf_restrictions],
            },
        }

def suggest_journal_publisher(request, field):
    term = request.GET.get('term', '')
    publishers = romeo.search_publisher_name(term, versions='all')
    suggestions = [publisher_suggestion_data(pub) for pub in publishers]
    return HttpResponse(json_serializer.encode(suggestions),
                        mimetype='application/json')
SUGGEST_FUNCTIONS['journal_publisher'] = suggest_journal_publisher

def publisher_details(request):
    publisher = None
    if 'romeo_id' in request.GET:
        publisher = romeo.search_publisher_id(request.GET['romeo_id'],
                versions='all')
    elif 'name' in request.GET:
        publishers = romeo.search_publisher_name(request.GET['name'],
                type='exact', versions='all')
        if publishers:
            publisher = publishers[0]

    if publisher is None:
        raise Http404

    data = publisher_suggestion_data(publisher)
    return HttpResponse(json_serializer.encode(data),
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

    template_name = 'publication/review-queue.html'
    # for ajax requests, only display the inner content
    if request.is_ajax():
        template_name = 'publication/snippets/review-queue.html'


    return render(request, template_name, {
        'results': results, 'show_pages': show_pages,
        })

def open_access_fund(request):
    '''
    A form for submitting an OA Fund Proposal
    '''
    template_name = 'publication/open_access_fund.html'

    form = None
    if request.POST:
        form = OpenAccessProposalForm(request.POST)
    else:
        form = OpenAccessProposalForm()

    if request.POST and form.is_valid():
        content = render_to_string('publication/email/oa_fund_proposal.txt', {
            'form': form
        })
        mail_managers('Open Access Fund Proposal from OpenEmory', content)
        #redirect
        return redirect('site-index')

    return render(request, template_name, {
        'form': form
    })
