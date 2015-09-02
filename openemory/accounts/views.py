# file openemory/accounts/views.py
# 
#   Copyright 2010 Emory University General Library
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

from collections import defaultdict
import hashlib
import logging
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.mail import mail_managers
from django.core.urlresolvers import reverse
from django.core.serializers.json import DjangoJSONEncoder
from django.contrib import messages
from django.contrib.auth import views as authviews
from django.contrib.auth.models import User
from django.contrib.sites.models import get_current_site
from django.template.loader import render_to_string
from django.db.models import Count, Q
from django.http import HttpResponse, Http404, HttpResponseForbidden, \
                        HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_http_methods
from eulcommon.djangoextras.http import HttpResponseSeeOtherRedirect, content_negotiation
from eulfedora.server import Repository
from eulfedora.views import login_and_store_credentials_in_session
from eullocal.django.emory_ldap.backends import EmoryLDAPBackend
from eulxml.xmlmap.dc import DublinCore
from rdflib.graph import Graph as RdfGraph
from rdflib import Namespace, URIRef, RDF, Literal, BNode
from taggit.utils import parse_tags
from taggit.models import Tag

from openemory.publication.models import Article, ArticleStatistics
from openemory.rdfns import FRBR, FOAF, ns_prefixes
from openemory.accounts.auth import login_required, require_self_or_admin
from openemory.accounts.forms import ProfileForm, InterestFormSet, FeedbackForm
from openemory.accounts.models import researchers_by_interest as users_by_interest, \
     Bookmark, articles_by_tag, Degree, EsdPerson, Grant, UserProfile, Announcement, Position
from openemory.util import paginate, solr_interface

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
        # NOTE: specifying 401.html because default accounts/registration.html
        # doesn't exist; we should handle this better
        template_name='401.html')
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

    Helper method for profile views (:meth:`rdf_profile` and
    :meth:`profile`).
    '''
    # FIXME: It made sense in the past to require an EsdPerson for every
    # User/UserProfile. As of 2012-03-06, this shouldn't be so important.
    # At some point we should make this work if the User and UserProfile
    # exist (assuming profile.has_profile_page()) even if the EsdPerson
    # doesn't.

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
    '''Display public profile information and publications for the requested
    author.  Uses content negotation to provide equivalent content via
    RDF (see :meth:`rdf_profile`).

    If a logged in author or site admin looks at the profile, a
    dashboard view is displayed instead of the public profile
    information.'''

    user, userprofile = _get_profile_user(username)

    # if request is from a logged in user looking at their own profile
    # or a site admin, return the faculty dashboard view
    if request.user.is_authenticated() and request.user == user \
           or request.user.has_perm('accounts.change_userprofile'):
        return render(request, 'accounts/dashboard.html', {'author': user})

    # otherwise, return the public profile
    else:
        return public_profile(request, username)


def public_profile(request, username):
    '''Display public profile information and publications for the
    requested author.

    When requested via AJAX, returns HTML that can be displayed inside
    a faculty dashboard tab.
    '''
    user, userprofile = _get_profile_user(username)

    form, interest_formset = None, None

    context = {}
    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=userprofile)
        interest_formset = InterestFormSet(request.POST, prefix='interests')
        if form.is_valid() and interest_formset.is_valid():
            # save and redirect to profile
            form.save(commit=False)
            new_interests = [f.cleaned_data.get('interest')
                             for f in interest_formset.forms
                             if f.cleaned_data.get('interest', '') and
                                not f.cleaned_data.get('DELETE', False)]
            userprofile.research_interests.set(*new_interests)
            # if a new photo file was posted, resize it
            if 'photo' in request.FILES:
                form.instance.resize_photo()
            userprofile.save()

            messages.success(request, 'Your profile was updated.')
            # TODO: might want a different behavior when POSTed via ajax
            return HttpResponseSeeOtherRedirect(reverse('accounts:dashboard-profile',
                                                        kwargs={'username': username}))
        else:
            context['invalid_form'] = True

    if (request.user.has_perm("accounts.change_userprofile") or request.user == user) and not request.method == 'POST':
        form = ProfileForm(instance=userprofile)
        form.inlineformsets
        interest_data = [{'interest': i}
                             for i in sorted(userprofile.research_interests.all())]
        interest_formset = InterestFormSet(initial=interest_data, prefix='interests')

    context.update({
        'author': user,
        'form': form,
        'interest_formset': interest_formset,
    })

    if request.is_ajax():
        # display a briefer version of the profile, for inclusion in faculty dash
        template_name = 'accounts/snippets/profile-tab.html'

    # for non-ajax requests, display full profile with documents
    else:
        # get articles where the user is the author
        articles_query = userprofile.recent_articles_query()
        paginated_articles, show_pages = paginate(request, articles_query)

        url_params = request.GET.copy()
        url_params.pop('page', None)
        context.update({
            'results': paginated_articles,
            'show_pages': show_pages,
            'url_params': url_params.urlencode(),
        })
        template_name = 'accounts/profile.html'

    return render(request, template_name, context)


@require_self_or_admin
def edit_profile(request, username):
    '''Display and process profile edit form.  On GET, displays the
    form; on POST, processes the form and saves if valid.  Currently
    redirects to profile view on success.

    When requested via AJAX, returns HTML that can be displayed in a
    dashboard tab; otherwise, returns the dashboard page with edit
    content loaded.
    '''

    user, userprofile = _get_profile_user(username)
    context = {'author': user}
    if request.method == 'GET':
        form = ProfileForm(instance=userprofile)
        interest_data = [{'interest': i}
                         for i in sorted(userprofile.research_interests.all())]
        interest_formset = InterestFormSet(initial=interest_data, prefix='interests')

    elif request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=userprofile)
        interest_formset = InterestFormSet(request.POST, prefix='interests')
        if form.is_valid() and interest_formset.is_valid():
            # save and redirect to profile
            form.save(commit=False)
            new_interests = [f.cleaned_data.get('interest')
                             for f in interest_formset.forms
                             if f.cleaned_data.get('interest', '') and
                                not f.cleaned_data.get('DELETE', False)]
            userprofile.research_interests.set(*new_interests)
            # if a new photo file was posted, resize it
            if 'photo' in request.FILES:
                form.instance.resize_photo()
            userprofile.save()

            # TODO: might want a different behavior when POSTed via ajax
            return HttpResponseSeeOtherRedirect(reverse('accounts:dashboard-profile',
                                                        kwargs={'username': username}))
        else:
            context['invalid_form'] = True

    context['form'] = form
    context['interest_formset'] = interest_formset

    # template for the tab-only portion
    template_name = 'accounts/snippets/edit-profile-tab.html'

    # for a non-ajax request, load the tab template in the dashboard
    if not request.is_ajax():
        context.update({'tab_template': template_name, 'tab': 'profile'})
        template_name = 'accounts/dashboard.html'


    return render(request, template_name, context)



@require_self_or_admin
def dashboard_summary(request, username):
    '''Display dashboard summary information for a logged-in faculty
    user looking at their own profile (or a site admin looking at any
    faculty profile).

    When requested via AJAX, returns HTML for the dashboard tab only;
    otherwise, returns the dashboard with tab content loaded.
    '''
    user, userprofile = _get_profile_user(username)
    # get articles where the user is the author
    articles_query = userprofile.recent_articles_query()
    paginated_articles, show_pages = paginate(request, articles_query)

    # collect all stats for articles
    user_stats = defaultdict(int)
    user_stats['total_items'] = paginated_articles.paginator.count
    # get individual stat records and add them up
    for article in paginated_articles.object_list:
        stats  = ArticleStatistics.objects.filter(pid=article['pid'])
        # FIXME: use django aggregations here?
        # (should aggregate stats be a function userprofile?)
        for stat in stats:
            user_stats['views'] += stat.num_views
            user_stats['downloads'] +=  stat.num_downloads

    announcements =  Announcement.get_displayable()

    context = {
        'author': user,
        'user_stats': user_stats,
        'unpublished_articles': userprofile.unpublished_articles(),
        'announcements': announcements
    }

    # template for the tab-only portion
    template_name = 'accounts/snippets/dashboard-tab.html'

    # for a non-ajax request, load the tab template in the dashboard
    if not request.is_ajax():
        context.update({'tab_template': template_name, 'tab': 'dashboard'})
        template_name = 'accounts/dashboard.html'

    return render(request, template_name, context)

@require_self_or_admin
def dashboard_documents(request, username):
    '''Display dashboard tab with documents for a logged-in faculty
    user looking at their own profile or a site admin looking at any
    faculty profile.

    When requested via AJAX, returns HTML for the dashboard tab only;
    otherwise, returns the dashboard with tab content loaded.
    '''
    user, userprofile = _get_profile_user(username)
    # get articles where the user is the author
    articles_query = userprofile.recent_articles_query()
    paginated_articles, show_pages = paginate(request, articles_query)

    url_params = request.GET.copy()
    url_params.pop('page', None)

    context = {
        'author': user,
        'results': paginated_articles,
        'show_pages': show_pages,
        'url_params': url_params.urlencode(),
        'unpublished_articles': userprofile.unpublished_articles()
    }

    # template for the tab-only portion
    template_name = 'accounts/snippets/documents-tab.html'

    # for a non-ajax request, load the tab template in the dashboard
    if not request.is_ajax():
        context.update({'tab_template': template_name, 'tab': 'documents'})
        template_name = 'accounts/dashboard.html'

    return render(request, template_name, context)


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


def position_autocomplete(request):
    '''Auto-complete for :class:`~openemory.accounts.model.Position`
    A.K.A. Institute Affiliations

    Autocompletion is based on ``term`` query string parameter.
    '''
    term = request.GET.get('term', '')
    # find position names with any match;
    term_filter = {'name__icontains': term} # filter based on mode

    # sort the most common matches first and get the counts
    results = Position.objects.filter(**term_filter) \
                         .values('name') \
                         .annotate(count=Count('name')) \
                         .order_by('-count')

    suggestions = [{'label': '%s (%s)' % (i['name'], i['count']),  'value': i['name']}
                   for i in results[:10]]

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
def faculty_autocomplete(request):
    term = request.GET.get('term', '')
    # handle multiple terms and strip off commas
    # e.g., if user searches for "lastname, firstname"
    terms = [t.strip(',') for t in term.lower().split() if t]
    # TODO: consider using eulcommon.searchutil here

    solr = solr_interface()
    # do an OR search for partial or exact matches in the full name
    term_filter = solr.Q()
    for t in terms:
        # exact match or partial match (exact word with * does not match)
        term_filter |= solr.Q(ad_name=t) | solr.Q(ad_name='%s*' % t)
    r = solr.query(term_filter).filter(record_type=EsdPerson.record_type) \
            .field_limit(['username', 'first_name',
                        'last_name', 'department_name',
                        'ad_name'], score=True) \
            .sort_by('-score').sort_by('ad_name_sort') \
            .paginate(rows=10).execute()

    # NOTE: may want to cut off based on some relevance score,
    # (e.g., if score is below 0.5 and there is at least one good match,
    # omit the less relevant items)
    suggestions = [
        {'label': u['ad_name'],  # directory name in lastname, firstname format
         'description': u.get('department_name', ''),  # may be suppressed
         'username': u['username'],
         # first name is missing in some cases-- don't error if it's not present
         # NOTE: if first name is missing, name may be listed/filled in wrong
         'first_name': u.get('first_name', ''),
         'last_name': u['last_name'],
         'affiliation': 'Emory University'}
         for u in r
        ]
    return  HttpResponse(json_serializer.encode(suggestions),
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


def departments(request):
    '''List department names based on Faculty information in ESD,
    grouped by division name.'''
    solr = solr_interface()
    div_dept_field = 'division_dept_id'
    r = solr.query(record_type=EsdPerson.record_type) \
            .facet_by(div_dept_field, limit=-1, sort='index') \
            .paginate(rows=0) \
            .execute()
    div_depts = r.facet_counts.facet_fields[div_dept_field]

    # division_dept_id field is indexed in Solr as
    # division_name|division_code|department_shortname|department_id
    # split out and convert to list of dict
    depts = []
    for d, total in div_depts:
        dept = EsdPerson.split_department(d)
        dept['total'] = total
        depts.append(dept)

    return render(request, 'accounts/departments.html',
                  {'departments': depts})

def view_department(request, id):
    '''View a list of faculty (or non-faculty users with profiles) in a
    single department.

    :param id: department id
    '''
    # get a list of people by department code
    dep_id = id
    solr = solr_interface()
    people = solr.query(department_id=id) \
                 .filter(record_type=EsdPerson.record_type) \
                 .sort_by('last_name') \
                 .paginate(rows=150).execute()
    filter = request.GET['filter'] if 'filter' in request.GET else ''

    q = solr.query(department_id=id).filter(content_model=Article.ARTICLE_CONTENT_MODEL,
                            state='A') \
                    .facet_by('creator_sorting', mincount=1, limit=-1, sort='index', prefix=filter.lower())
    result = q.paginate(rows=0).execute()
    facets = result.facet_counts.facet_fields['creator_sorting']

    #removes name from field for proper presentation
    facets = [(name.split("|")[1], count) for name, count in facets]


    if len(people):
        division = people[0]['division_name']
        depts = people[0]['department_name']
        # department_name is a list since an article can have 0..n. An
        # EsdPerson, though, only has one, so just grab the first.
        dept = depts[0] if depts else ''
        # shorten department name for display, since we have division
        # name for context
        if ':' in dept:
            dept = dept[dept.rfind(':')+1:].strip()

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
                  {'esdpeople': people, 'department': dept, 'division': division, 'facets':facets, 'dep_id':dep_id})

@login_required
def admin_dashboard(request):
    '''Admin dashboard to provide access to various admin
    functionality in one place.  Based on the faculty dashboard.
    '''

    # TODO: possibly add a dashboard summary tab?  number of items
    # published/unpublished/unreviewed queue size for harvest/review
    # possibly re-use site statistics content...

    return render(request, 'accounts/admin_dashboard.html')


def feedback(request):
    user = request.user

    if request.method == 'POST':
        form = FeedbackForm(request.POST)
        if form.is_valid():
            user_name = user.username if user.is_authenticated() else 'anonymous user'
            user_email = form.cleaned_data['email']
            user_subject = ' ' if not form.cleaned_data['subject'] else ' %s '% form.cleaned_data['subject'].strip()

            subject = 'OpenEmory site feedback:%sfrom %s' % (user_subject, user_name)
            content = render_to_string('accounts/feedback-email.txt',
                    {
                     'user': request.user,
                     'form_data': form.cleaned_data,
                     'site': get_current_site(request),
                    })

            mail_managers(subject, content)

            destination = reverse('site-index')
            try:
                if user.is_authenticated():
                    profile = user.get_profile()
                    if profile.has_profile_page():
                        destination = reverse('accounts:profile',
                                kwargs={'username': user.username})
            except:
                pass # no user, or no profile. just use the default destination

            messages.success(request, "Thanks for your feedback! We've sent it to our site admins.")
            return HttpResponseRedirect(destination)

    else:
        form_data = {}
        if user.is_authenticated():
            try:
                profile = user.get_profile()
                esd = profile.esd_data()
                form_data['name'] = esd.directory_name
                form_data['email'] = esd.email
                form_data['phone'] = esd.phone
            except EsdPerson.DoesNotExist:
                # profile, but no esd
                form_data['name'] = user.get_full_name()
                form_data['email'] = user.email
        form = FeedbackForm(initial=form_data)

    return render(request, 'accounts/feedback.html', {'form': form})
