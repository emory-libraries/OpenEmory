from django.conf import settings
from django.core.urlresolvers import reverse
from django.core.serializers.json import DjangoJSONEncoder
from django.contrib import messages
from django.contrib.auth import views as authviews
from django.contrib.auth.models import User
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_http_methods
from eulcommon.djangoextras.http import HttpResponseSeeOtherRedirect, content_negotiation
from eulfedora.server import Repository
from eulfedora.views import login_and_store_credentials_in_session
from eulxml.xmlmap.dc import DublinCore
from rdflib.graph import Graph as RdfGraph
from rdflib import Namespace, URIRef, RDF, Literal, BNode
from sunburnt import sunburnt
from taggit.utils import parse_tags
from taggit.models import Tag

from openemory.publication.models import Article
from openemory.rdfns import FRBR, FOAF, ns_prefixes
from openemory.util import solr_interface
from openemory.accounts.forms import TagForm
from openemory.accounts.models import researchers_by_interest as users_by_interest

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

            # otherwise, redirect to the user's own profile page
            else:
                next_url = reverse('accounts:profile',
                                   kwargs={'username': request.user.username})
            
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


def rdf_profile(request, username):
    '''Profile information comparable to the human-readable content
    returned by :meth:`profile`, but in RDF format.'''

    # retrieve user & publications - same logic as profile above
    user = get_object_or_404(User, username=username)
    articles = user.get_profile().recent_articles(limit=10)

    # build an rdf graph with information author & publications
    rdf = RdfGraph()
    for prefix, ns in ns_prefixes.iteritems():
        rdf.bind(prefix, ns)
    author_node = BNode()
    profile_uri = URIRef(request.build_absolute_uri(reverse('accounts:profile',
                                                    kwargs={'username': username})))

    rdf.add((profile_uri, FOAF.primaryTopic, author_node))
    rdf.add((author_node, FOAF.nick, Literal(user.username)))
    # add information about the person
    rdf.add((author_node, RDF.type, FOAF.Person))
    rdf.add((author_node, FOAF.name, user.get_full_name()))
    rdf.add((author_node, FOAF.publications, profile_uri))
    # initialize objects from Fedora so we can get RDF info
    repo = Repository(request=request)
    # add RDF for each article to the graph
    for record in articles:
        obj = repo.get_object(record['pid'], type=Article)
        rdf += obj.as_rdf()
        # add relation between author and document
        # some redundancy here, for now
        rdf.add((author_node, FRBR.creatorOf, obj.uriref))
        rdf.add((author_node, FOAF.made, obj.uriref))
    return HttpResponse(rdf.serialize(), content_type='application/rdf+xml')

@content_negotiation({'application/rdf+xml': rdf_profile})
def profile(request, username):
    '''Display profile information and publications for the requested
    author.  Uses content negotation to provide equivalent content via
    RDF (see :meth:`rdf_profile`).'''
    # retrieve the db record for the requested user
    user = get_object_or_404(User, username=username)
    context = {
        'author': user,
        'articles': user.get_profile().recent_articles(limit=10)
    }
    # if a logged-in user is viewing their own profile, pass
    # tag edit form and editable flag to to the template
    if request.user.is_authenticated() and request.user == user:
        tags = ', '.join(tag.name for tag in user.get_profile().research_interests.all())
        context.update({
            # add trailing comma so jquery will not attempt to auto-complete existing tag
            'tagform': TagForm(initial={'tags': '%s, ' % tags}), 
            'editable_tags':  True
        })
    
    return render(request, 'accounts/profile.html', context)

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
        if request.method == 'PUT':
            user.get_profile().research_interests.set(*tags)
        elif request.method == 'POST':
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
    users = users_by_interest(slug=tag)
    return render(request, 'accounts/research_interest.html', {'interest': tag,
                                                               'users': users})    
def interests_autocomplete(request):
    '''Auto-complete for user profile research interests.  Finds tags
    that are currently in use as
    :class:`~openemory.accounts.models.UserProfile` research interests
    that contain the specified search term (case-insensitive), and
    returns the 10 most common ones as a JSON list, with a tag id
    (slug), display label (tag name and count), and the value to be
    used (tag name). Return format is suitable for use with `JQuery UI
    Autocomplete`_ widget.

    .. _JQuery UI Autocomplete: http://jqueryui.com/demos/autocomplete/
    
    '''
    term = request.GET['s']
    # find tags attached to user profiles that contain the search term
    tag_qs = Tag.objects.filter(userprofile__isnull=False).filter(name__icontains=term)
    # annotate the query string with a count of the number of profiles with that tag,
    # order so most commonly used tags will be listed first
    annotated_qs = tag_qs.annotate(count=Count('userprofile')).order_by('-count')
    # generate a dictionary to return via json with id, label (including count), value
    tags = [{'id': tag.slug,
             'label': '%s (%d)' % (tag.name, tag.count),
             'value': tag.name}
            for tag in annotated_qs[:10]	# limit to the first 10 tags
           ]
    return  HttpResponse(json_serializer.encode(tags),
                         mimetype='application/json')
    
