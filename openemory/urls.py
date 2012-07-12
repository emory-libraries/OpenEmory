from django.conf import settings
from django.conf.urls.defaults import patterns, include, url
from django.contrib import admin
from django.views.generic.simple import direct_to_template

from openemory.accounts.sitemaps import ProfileSitemap
from openemory.publication.sitemaps import ArticleSitemap

admin.autodiscover()

sitemaps = {
    'articles': ArticleSitemap,
    'profiles': ProfileSitemap,
}

urlpatterns = patterns('',
    url(r'^$', 'openemory.publication.views.site_index',  name='site-index'),
    url('^feedback/$', 'openemory.accounts.views.feedback', name='feedback'),
    url(r'^publications/', include('openemory.publication.urls', namespace='publication')),
    url(r'^harvest/', include('openemory.harvest.urls', namespace='harvest')),
    # django db admin
    url(r'^db-admin/doc/', include('django.contrib.admindocs.urls')),
    url(r'^db-admin/', include(admin.site.urls)),
    # indexdata
    url(r'^indexdata/', include('eulfedora.indexdata.urls', namespace='indexdata')),
    # accounts app includes several top-level urls
    url(r'^', include('openemory.accounts.urls', namespace='accounts')),
    url(r'^sitemap\.xml$', 'django.contrib.sitemaps.views.sitemap',
        {'sitemaps': sitemaps}),
    url(r'^robots.txt$', 'django.views.generic.simple.direct_to_template',
        {'template': 'robots.txt'}),
)

if settings.DEBUG:
    urlpatterns += patterns('',
        url(r'^media/(?P<path>.*)$', 'django.views.static.serve', {
            'document_root': settings.MEDIA_ROOT,
        }),
    )
