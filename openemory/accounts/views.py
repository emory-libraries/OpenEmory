from django.conf import settings
from django.core.urlresolvers import reverse
from django.contrib.auth import views as authviews
from django.contrib.auth.models import User
from django.shortcuts import render, get_object_or_404
from sunburnt import sunburnt

from openemory.publication.models import Article

def logout(request):
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
                  {'results': results, 'owner': user})
