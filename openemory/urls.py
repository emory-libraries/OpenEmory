from django.conf import settings
from django.conf.urls.defaults import patterns, include, url
from django.contrib import admin
from django.views.generic.simple import direct_to_template

admin.autodiscover()

urlpatterns = patterns('',
    url(r'^$', 'openemory.publication.views.site_index',  name='site-index'),
    url('^feedback/$', direct_to_template, {'template': 'feedback.html'}, name='feedback'),
    url(r'^publications/', include('openemory.publication.urls', namespace='publication')),
    url(r'^harvest/', include('openemory.harvest.urls', namespace='harvest')),
    # django db admin
    url(r'^db-admin/doc/', include('django.contrib.admindocs.urls')),
    url(r'^db-admin/', include(admin.site.urls)),
    # indexdata
    url(r'^indexdata/', include('eulfedora.indexdata.urls', namespace='indexdata')),
    # accounts app includes several top-level urls
    url(r'^', include('openemory.accounts.urls', namespace='accounts')),
)

if settings.DEBUG:
    urlpatterns += patterns('',
        url(r'^media/(?P<path>.*)$', 'django.views.static.serve', {
            'document_root': settings.MEDIA_ROOT,
        }),
    )
