from django.conf.urls.defaults import patterns, include, url
from openemory.publication import views

urlpatterns = patterns('',
    url(r'^new/$', views.ingest, name='ingest'),
    url(r'^(?P<pid>[^/]+)/edit/$', views.edit_metadata, name='edit'),
    url(r'^(?P<pid>[^/]+)/pdf/$', views.download_pdf, name='pdf'),
    # raw datastream view; add other dsids here as appropriate
    url(r'^(?P<pid>[^/]+)/(?P<dsid>contentMetadata)/$', views.view_datastream, name='ds'),
)
