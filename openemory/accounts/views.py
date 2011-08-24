from django.conf import settings
from django.core.urlresolvers import reverse
from django.contrib.auth import views as authviews
from django.contrib.auth.models import User
from django.shortcuts import render, get_object_or_404
from eulcommon.djangoextras.http import HttpResponseSeeOtherRedirect
from eulfedora.views import login_and_store_credentials_in_session
from sunburnt import sunburnt

from openemory.publication.models import Article

def login(request):
    '''Log in, store credentials for Fedora access, and redirect to
    the user profile page if no "next" url was specified.

    Login functionality based on
    :meth:`eulfedora.views.login_and_store_crendtials_in_session` and
    :meth:`django.contrib.auth.views.login`
    '''
    response = login_and_store_credentials_in_session(request,
        # NOTE: specifying index.html because default accounts/registration.html
        # doesn't exist; we should handle this better
        template_name='index.html')
    # if login succeeded and a next url was not specified,
    # redirect to the user's profile page
    if request.method == "POST" and request.user.is_authenticated() \
           and 'next' not in request.POST:
        return HttpResponseSeeOtherRedirect(reverse('accounts:profile',
                                                    kwargs={'username': request.user.username}))

    return response

def logout(request):
    'Log out and redirect to the site index page.'
    return authviews.logout(request, next_page=reverse('site-index'))

def profile(request, username):
    # retrieve the db record for the requested user
    user = get_object_or_404(User, username=username)
    # search solr for articles owned by the specified user
    solr = sunburnt.SolrInterface(settings.SOLR_SERVER_URL)
    # - filtering separately should allow solr to cache filtered result sets more effeciently
    # - for now, sort so most recently modified are at the top
    solrquery = solr.query(owner=username).filter(
        content_model=Article.ARTICLE_CONTENT_MODEL).sort_by('-last_modified')
    results = solrquery.execute()
    return render(request, 'accounts/profile.html',
                  {'results': results, 'author': user})
