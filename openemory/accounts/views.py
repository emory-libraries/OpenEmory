import hashlib
import logging
from django.conf import settings
from django.core.urlresolvers import reverse
from django.core.serializers.json import DjangoJSONEncoder
from django.contrib import messages
from django.contrib.auth import views as authviews
from django.contrib.auth.models import User
from django.db.models import Count
from django.http import HttpResponse, Http404
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_http_methods
from eulcommon.djangoextras.http import HttpResponseSeeOtherRedirect, content_negotiation
from eulfedora.server import Repository
from eulfedora.views import login_and_store_credentials_in_session
from eullocal.django.emory_ldap.backends import EmoryLDAPBackend
from eulxml.xmlmap.dc import DublinCore
from rdflib.graph import Graph as RdfGraph
from rdflib import Namespace, URIRef, RDF, Literal, BNode
from sunburnt import sunburnt
from taggit.utils import parse_tags
from taggit.models import Tag

from openemory.publication.models import Article
from openemory.rdfns import FRBR, FOAF, ns_prefixes
from openemory.accounts.auth import login_required, require_self_or_admin
from openemory.accounts.forms import TagForm, ProfileForm
from openemory.accounts.models import researchers_by_interest as users_by_interest, \
     Bookmark, articles_by_tag, Degree, EsdPerson, Grant, UserProfile
from openemory.util import paginate

logger = logging.getLogger(__name__)

json_serializer = DjangoJSONEncoder(ensure_ascii=False, indent=2)

def login(request):
    '''Log in, store credentials for Fedora access, and redirect to
    the user profile page if no **next** url was specified.  If login
    fails, the user will be redirect either to the **next** url (if
    specified) or to the site index, with an error message to indicate
    the login failure.

    Login functionality is based on
    :meth:`eulfedora.views.login_and_store_credentials_in_session` and
    :meth:`django.contrib.auth.views.login`
    '''
    response = login_and_store_credentials_in_session(request,
        # NOTE: specifying index.html because default accounts/registration.html
        # doesn't exist; we should handle this better
        template_name='index.html')
    # if login succeeded and a next url was not specified,
    # redirect the user somewhere appropriate
    if request.method == "POST":
        next_url = request.POST.get('next', None)
        if request.user.is_authenticated() and not next_url:
            # if the user is in the Site Admin group, redirect
            # to the harvest queue page
            if request.user.groups.filter(name='Site Admin').count():
                next_url = reverse('harvest:queue')

            # if the user has a profile page, redirect t
            elif request.user.get_profile().has_profile_page():
                next_url = reverse('accounts:profile',
                                   kwargs={'username': request.user.username})
                
            if next_url is None:
                next_url = reverse('site-index')
            
            return HttpResponseSeeOtherRedirect(next_url)

        # if this was a post, but the user is not authenticated, login must have failed
        elif not request.user.is_authenticated():
            # add an error message, then redirect the user back to where they were
            messages.error(request, 'Login failed. Please try again.')
            if not next_url:
                next_url = reverse('site-index')
            return HttpResponseSeeOtherRedirect(next_url)

    return response

def logout(request):
    'Log out and redirect to the site index page.'
    return authviews.logout(request, next_page=reverse('site-index'))


def _get_profile_user(username):
    '''Find the :class:`~django.contrib.auth.models.User` and
    :class:`~openemory.accounts.models.UserProfile` for a specified
    username, for use in profile pages.  The specified ``username``
    must exist as an :class:`~openemory.accounts.models.EsdPerson`; if
    the corresponding :class:`~openemory.accounts.models.UserProfile`
    does not yet exist, it will be initialized from LDAP.

    Raises a :class:`django.http.Http404` if any of the models cannot
    be found or created.

    Helper method for profile views (:meth:`rdf_profile`,
    :meth:`profile`, and :meth:`edit_profile`).
    '''
    # retrieve the ESD db record for the requested user
    esdperson = get_object_or_404(EsdPerson, netid=username.upper())
    # get the corresponding local profile & user
    try:
        profile = esdperson.profile()
        user = profile.user
        # 404 if the user exists but should not have a profile page
        # (check against UserProfile if there is one, for local profile override)
        if not profile.has_profile_page():
            raise Http404
    except UserProfile.DoesNotExist:
        # if local account doesn't exist, make sure ESD indicates the
        # user should have a profile before proceeding
        if not esdperson.has_profile_page():
            raise Http404
        
        # local account doesn't exist but user should have a profile:
        # attempt to init local user & profile
        
        backend = EmoryLDAPBackend()
        user_dn, user = backend.find_user(username)
        if not user:
            raise Http404
        profile = user.get_profile()

    return user, profile
    


def rdf_profile(request, username):
    '''Profile information comparable to the human-readable content
    returned by :meth:`profile`, but in RDF format.'''

    # retrieve user & publications - same logic as profile above
    user, userprofile = _get_profile_user(username)
    articles = userprofile.recent_articles(limit=10)

    # build an rdf graph with information author & publications
    rdf = RdfGraph()
    for prefix, ns in ns_prefixes.iteritems():
        rdf.bind(prefix, ns)
    author_node = BNode()
    profile_uri = URIRef(request.build_absolute_uri(reverse('accounts:profile',
                                                    kwargs={'username': username})))
    profile_data_uri = URIRef(request.build_absolute_uri(reverse('accounts:profile-data',
                                                         kwargs={'username': username})))

    # author information
    rdf.add((profile_uri, FOAF.primaryTopic, author_node))
    rdf.add((author_node, RDF.type, FOAF.Person))
    rdf.add((author_node, FOAF.nick, Literal(user.username)))
    rdf.add((author_node, FOAF.publications, profile_uri))

    try:
        esd_data = userprofile.esd_data()
    except EsdPerson.DoesNotExist:
        esd_data = None

    if esd_data:
        rdf.add((author_node, FOAF.name, Literal(esd_data.directory_name)))
    else:
        rdf.add((author_node, FOAF.name, Literal(user.get_full_name())))

    if esd_data and not userprofile.suppress_esd_data:
        mbox_sha1sum = hashlib.sha1(esd_data.email).hexdigest()
        rdf.add((author_node, FOAF.mbox_sha1sum, Literal(mbox_sha1sum)))
        if esd_data.phone:
            rdf.add((author_node, FOAF.phone, URIRef('tel:' + esd_data.phone)))

    # TODO: use ESD profile data where appropriate
    # (and honor internet/directory suppressed, suppression override)

    # article information
    repo = Repository(request=request)
    for record in articles:
        obj = repo.get_object(record['pid'], type=Article)
        obj_node = BNode() # info:fedora/ uri is not public

        # relate to author
        rdf.add((author_node, FRBR.creatorOf, obj_node))
        rdf.add((author_node, FOAF.made, obj_node))
        # add object rdf
        rdf += obj.as_rdf(node=obj_node)

    response = HttpResponse(rdf.serialize(), content_type='application/rdf+xml')
    response['Content-Location'] = profile_data_uri
    return response




@content_negotiation({'application/rdf+xml': rdf_profile})
def profile(request, username):
    '''Display profile information and publications for the requested
    author.  Uses content negotation to provide equivalent content via
    RDF (see :meth:`rdf_profile`).'''

    user, userprofile = _get_profile_user(username)
    context = {
        'author': user,
        'articles': userprofile.recent_articles(limit=10)
    }
    # if a logged-in user is viewing their own profile, pass
    # tag edit form and editable flag to to the template,
    # and check for any unpublished articles
    if request.user.is_authenticated() and (request.user == user or request.user.is_superuser):
        tags = ', '.join(tag.name for tag in userprofile.research_interests.all())
        if tags:
            # add trailing comma so jquery will not attempt to auto-complete existing tag
            tagform_initital = {'tags': '%s, ' % tags}
        else:
            tagform_initital = {}
        context.update({
            'tagform': TagForm(initial=tagform_initital), 
            'editable_tags':  True,
            'unpublished_articles': userprofile.unpublished_articles()
        })
    # TODO: display unpublished articles for admin users too
    
    return render(request, 'accounts/profile.html', context)

@require_self_or_admin
@require_http_methods(['GET', 'POST'])
def edit_profile(request, username):
    '''Edit details and settings for an author profile.'''
    # retrieve the db record for the requested user
    user, userprofile = _get_profile_user(username)
    
    if request.method == 'GET':
        form = ProfileForm(instance=userprofile)

    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=userprofile)
        if form.is_valid():
            # save and redirect to profile
            form.save()
            return HttpResponseSeeOtherRedirect(reverse('accounts:profile',
                                                kwargs={'username': username}))

    # display form on GET or invalid POST
    return render(request, 'accounts/edit_profile.html',
                  {'form': form, 'author': user})
            

@require_http_methods(['GET', 'PUT', 'POST'])
def profile_tags(request, username):
    '''Add & display tags (aka research interests) on a user profile.

    On an HTTP GET, returns a JSON list of the tags for the specified
    user profile.

    On an HTTP PUT, if the requesting user is logged in and adding
    tags to their own profile, will replace any existing tags with
    tags from the body of the request.  Uses
    :meth:`taggit.utils.parse_tags` to parse tags, with the same logic
    :mod:`taggit` uses for parsing keyword and phrase tags on forms.
    After a successul PUT, returns the a JSON response with the
    updated tags and their corresponding urls.

    On an HTTP POST, performs the same tag parsing and permission
    checking as for PUT, but *adds* the POSTed tags to any existing
    tags instead of replacing them.
    
    '''
    user = get_object_or_404(User, username=username)
    # check authenticated user
    if request.method in ['PUT', 'POST']: 
        if not request.user.is_authenticated() or request.user != user:
            if not request.user.is_authenticated():
                # user is not logged in 
                code, message = 401, 'Not Authorized'
            else:
                # user is authenticated but not allowed
                code, message = 403, 'Permission Denied'
            return HttpResponse(message, mimetype='text/plain',
                                status=code)
        # user is authenticated and request user is the user being tagged
        tags = parse_tags(request.read())
        if request.method == 'PUT':	# replace tags with new set
            user.get_profile().research_interests.set(*tags)
        elif request.method == 'POST':	# add new tag to existing tags
            user.get_profile().research_interests.add(*tags)
            
        # fall through to GET handling and display the newly-updated tags
        
    # GET or successful PUT/POST
    tags = dict([(tag.name, reverse('accounts:by-interest', kwargs={'tag': tag.slug}))
                  for tag in user.get_profile().research_interests.all()])
    return  HttpResponse(json_serializer.encode(tags),
                         mimetype='application/json')

def researchers_by_interest(request, tag):
    '''Find users by research interest.

    :param tag: slug value for the research interest tag
    '''
    tag = get_object_or_404(Tag, slug=tag)
    users = users_by_interest(slug=tag.slug)
    return render(request, 'accounts/research_interest.html', {'interest': tag,
                                                               'users': users})    
def interests_autocomplete(request):
    '''Auto-complete for user profile research interests.  Finds tags
    that are currently in use as
    :class:`~openemory.accounts.models.UserProfile` research interests.
    
    See documentation on :meth:`tag_autocompletion` for more details.
    '''
    tag_qs = Tag.objects.filter(taggit_taggeditem_items__content_type__model='userprofile')
    # NOTE: using content-type filter because filtering on
    # userprofile__isnull=False incorrectly includes bookmark tags
    return tag_autocompletion(request, tag_qs, 'userprofile__user__id')


def degree_autocomplete(request, mode):
    '''Auto-complete for :class:`~openemory.accounts.model.Degree`
    institutions and degree names.

    Autocompletion is based on ``term`` query string parameter.

    :param mode: autocomplete mode - supported values are
    	``instutition`` or ``name``
    '''
    if mode not in ['institution', 'name']:
        raise Http404
        
    term = request.GET.get('term', '')
    # find degree institutions or degree names with any match;
    term_filter = {'%s__icontains' % mode: term} # filter based on mode
    # sort the most common matches first
    results = Degree.objects.filter(**term_filter).values(mode) \
                         .annotate(count=Count('pk')) \
                         .order_by('-count') 
    suggestions = [{'label': i[mode], 'value': i[mode]}
                   for i in results[:10]
                   ]
    return  HttpResponse(json_serializer.encode(suggestions),
                         mimetype='application/json')


def grant_autocomplete(request):
    term = request.GET.get('term', '')
    results = Grant.objects.filter(grantor__icontains=term) \
                    .values('grantor') \
                    .annotate(count=Count('pk')) \
                    .order_by('-count')
    suggestions = [i['grantor'] for i in results[:10]]
    return HttpResponse(json_serializer.encode(suggestions),
                         mimetype='application/json')


@login_required
def tags_autocomplete(request):
    '''Auto-complete for private tags.  Finds tags that the currently
    logged-in user has used for any of their
    :class:`~openemory.accounts.models.Bookmark` s.

    See documentation on :meth:`tag_autocompletion` for more details.
    '''
    tag_qs = Tag.objects.filter(bookmark__user=request.user)
    return tag_autocompletion(request, tag_qs, 'bookmark__user')

def tag_autocompletion(request, tag_qs, count_field):
    '''Common autocomplete functionality for tags.  Given a
    :class:`~taggit.models.Tag` QuerySet and a field to count, returns
    a distinct list of the 10 most common tags filtered on the 
    specified search term (case-insensitive).  Results are returned as
    JSON, with a tag id (slug), display label (tag name and count),
    and the value to be used (tag name) for each matching tag
    found. Return format is suitable for use with `JQuery UI
    Autocomplete`_ widget.

    .. _JQuery UI Autocomplete: http://jqueryui.com/demos/autocomplete/

    Single term autocompletion is based on ``s`` query string
    parameter.  If ``s`` is empty, this method will check for a
    ``term`` parameter and use :meth:`taggit.utils.parse_tags` to do
    tag autocompletion on the last tag in a list of tags.

    :param request: the http request passed to the original view
        method (used to retrieve the search term)
            
    :param tag_qs: a :class:`~taggit.models.Tag` QuerySet filtered to
        the appropriate set of tags (for further filtering by search term)
        
    :param count_field: field to be used for count annotation - used
         for tag ordering (most-used tags first) and display in the 
         autocompletion
    
    '''
    term = request.GET.get('s', '')
    prefix = suffix = ''
    if term == '':
        term = request.GET.get('term', '')
        if ',' in term:
            # NOTE: taggit has a parse_tags method, but unfortunately
            # it *sort* the tags, so we can't use it to identify the last term
            last_index = term.rfind(',') + 1
            # preserve the original string for inclusion in selected value
            prefix = term[:last_index + 1] 
            term = term[last_index+1:].strip()
            suffix = ', '
            
    # find tags attached to user profiles that contain the search term
    tag_qs = tag_qs.distinct().filter(name__icontains=term)
    # annotate the query string with a count of the number of profiles with that tag,
    # order so most commonly used tags will be listed first
    annotated_qs = tag_qs.annotate(count=Count(count_field)).order_by('-count')
    # generate a dictionary to return via json with id, label (including count), value
    tags = [{'id': tag.slug,
             'label': '%s (%d)' % (tag.name, tag.count),
             'value': ''.join([prefix, tag.name, suffix]) }
            for tag in annotated_qs[:10]	# limit to the first 10 tags
           ]
    return  HttpResponse(json_serializer.encode(tags),
                         mimetype='application/json')
    

@login_required
@require_http_methods(['GET', 'PUT'])
def object_tags(request, pid):
    '''Set & display private tags on a particular
    :class:`~eulfedora.models.DigitalObject` (saved in the database by
    way of :class:`~openemory.accounts.models.Bookmark`).

    On an HTTP GET, returns a JSON list of the tags for the specified
    object, or 404 if the object has not been tagged.

    On an HTTP PUT, will replace any existing tags with tags from the
    body of the request.  Uses :meth:`taggit.utils.parse_tags` to
    parse tags, with the same logic :mod:`taggit` uses for parsing
    keyword and phrase tags on forms.  After a successul PUT, returns
    the a JSON response with a list of the updated tags.  If the
    Fedora object does not exist, returns a 404 error.
    '''

    # bookmark options that will be used to create a new or find an
    # existing bookmark for either GET or PUT
    bkmark_opts = {'user': request.user, 'pid': pid}

    status_code = 200	# if all goes well, unless creating a new bookmark
    
    if request.method == 'PUT':
        # don't allow tagging non-existent objects
        # NOTE: this will 404 if a bookmark is created and an object
        # subsequently is removed or otherwise becomes unavailable in
        # the repository
        repo = Repository(request=request)
        obj = repo.get_object(pid)
        # if this fedora API call becomes expensive, may want to
        # consider querying Solr instead
        if not obj.exists:
            raise Http404

        bookmark, created = Bookmark.objects.get_or_create(**bkmark_opts)
        if created:
            status_code = 201
        bookmark.tags.set(*parse_tags(request.read()))
        # fall through to GET handling and display the newly-updated tags
        # should we return 201 when creating a new bookmark ? 

    if request.method == 'GET':
        bookmark = get_object_or_404(Bookmark, **bkmark_opts)
        
        
    # GET or successful PUT
    tags = [tag.name for tag in bookmark.tags.all()]
    return  HttpResponse(json_serializer.encode(tags), status=status_code,
                         mimetype='application/json')

@login_required
def tagged_items(request, tag):
    tag = get_object_or_404(Tag, slug=tag)
    articles = articles_by_tag(request.user, tag)
    results, show_pages = paginate(request, articles)

    context = {
        'tag': tag,
        'articles': results,
        'show_pages': show_pages,
    }
    return render(request, 'accounts/tagged_items.html', context)


@require_http_methods(['GET'])
def user_name(request, username):
    """Return a user's name.  If
    the user is not found in the local database, looks them up in LDAP
    (and initializes the user in the local database if successful).
    Returns a 404 if no user could be found.
    
    This view currently only returns JSON data intended for use in
    Ajax requests.
    """
    user_qs = User.objects.filter(username=username)
    if not user_qs.exists():
        ldap = EmoryLDAPBackend()
        # log ldap requests; using repr so it is evident when ldap is a Mock
        logger.debug('Looking up user in LDAP by username \'%s\' (using %r)' \
                     % (username, ldap))
        # find the user in ldap, and initialize in local db if found
        user_dn, user = ldap.find_user(username)
        # user not found in local db or in ldap
        if not user:
            raise Http404
    else:
        user = user_qs.get()

    data = {
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name
    }
    return  HttpResponse(json_serializer.encode(data),
                         mimetype='application/json')


    

def departments(request):
    '''List department names from ESD, grouped by division name.'''
    # sort by division, then department
    sort_fields = ['division_name', 'department_name']
    # return both division & department names, dept. id for link
    fields = ['division_name', 'department_name',
                     'department_id']
    # get a distinct list of division and department names only
    depts = EsdPerson.objects.filter(person_type='F').values(*fields)\
                .order_by(*sort_fields).distinct()
    # Some department names include abbreviated prefixes for their
    # division/school, e.g. SOM: for divisions in School of Medicine.
    # Since they'll be displayed with their division, strip out the
    # first prefix only.
    # NOTE: could have performances issues with full ESD
    for d in depts:
        if ':' in d['department_name']:
            dept = d['department_name']
            d['department_name'] = dept[dept.find(':')+1:].strip()

    # resort based on un-prefixed department names
    depts = sorted(depts, key=lambda k: '%s %s' % (k['division_name'],
                                                   k['department_name']))

    return render(request, 'accounts/departments.html',
                  {'departments': depts})

def view_department(request, id):
    '''View a list of aculty (or non-faculty users with profiles) in a
    single department.

    :param id: department id
    '''
    # get a list of people by department code
    # - restrict to faculty (only get people who will have profiles)
    # NOTE: when we add support for non-faculty profiles,
    # also look for users with local profile override
    people = EsdPerson.objects.filter(department_id=id).filter(person_type='F')
    # division & department should be the same for all; grab from first one
    if people:
        division = people[0].division_name
        dept = people[0].department_shortname
    else:
        # it's possible no profile users were found (unlikely with real data)
        # if no users were found, look up department code to get
        # division & department names 
        deptinfo = EsdPerson.objects.filter(department_id=id)\
                   	.only('department_name', 'division_name').distinct()
        # no department found for that id - 404
        if not deptinfo:
            raise Http404
        deptinfo = deptinfo[0]
        division = deptinfo.division_name
        dept = deptinfo.department_shortname
    return render(request, 'accounts/department.html',
                  {'esdpeople': people, 'department': dept, 'division': division})
