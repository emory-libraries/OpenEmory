from django.conf import settings
from django.conf.urls.defaults import patterns, include, url
from django.contrib import admin
from django.views.generic.simple import direct_to_template

admin.autodiscover()

urlpatterns = patterns('',
    url(r'^$', direct_to_template, {'template': 'index.html'}, name='site-index'),
    url(r'^publications/', include('openemory.publication.urls', namespace='publication')),
    url(r'^accounts/', include('openemory.accounts.urls', namespace='accounts')),
    # django db admin
    url(r'^db-admin/doc/', include('django.contrib.admindocs.urls')),
    url(r'^db-admin/', include(admin.site.urls)),
    # indexdata
    url(r'^indexdata/', include('eulfedora.indexdata.urls', namespace='indexdata')),
)
