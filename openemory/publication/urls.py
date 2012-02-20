from django.conf.urls.defaults import patterns, include, url
from openemory.publication import views

urlpatterns = patterns('',
    url(r'^summary/$', views.summary, name='summary'),
    url(r'^(?P<field>(authors|subjects|journals))/$', views.browse_field, name='browse'),
    url(r'^new/$', views.ingest, name='ingest'),
    url(r'^search/$', views.search, name='search'),
    url(r'^unreviewed/$', views.review_queue, name='review-list'),
    url(r'^(?P<pid>[^/]+)/$', views.view_article, name='view'),
    url(r'^(?P<pid>[^/]+)/edit/$', views.edit_metadata, name='edit'),
    url(r'^(?P<pid>[^/]+)/pdf/$', views.download_pdf, name='pdf'),
    # raw datastream view; add other dsids here as appropriate
    url(r'^(?P<pid>[^/]+)/(?P<dsid>contentMetadata|descMetadata|provenanceMetadata)/$',
        views.view_datastream, name='ds'),
    url(r'^(?P<pid>[^/]+)/(?P<dsid>authorAgreement)/$',
        views.view_private_datastream, name='private_ds'),
    url(r'^(?P<field>(funder|keyword|journal_title|journal_publisher|author_affiliation))/autocomplete/$',
        views.suggest, name='suggest'),
)
