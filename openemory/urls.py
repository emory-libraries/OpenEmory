from django.conf import settings
from django.conf.urls.defaults import patterns, include, url
from django.views.generic.simple import direct_to_template

urlpatterns = patterns('',
    url(r'^$', direct_to_template, {'template': 'index.html'}, name='site-index'),
    url(r'^publications/', include('openemory.publication.urls', namespace='publication')),
    url(r'^accounts/', include('openemory.accounts.urls', namespace='accounts')),   
)
