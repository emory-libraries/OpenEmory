# file openemory/publication/urls.py
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

from django.conf.urls.defaults import patterns, url
from openemory.publication import views

urlpatterns = patterns('',
    url(r'^summary/$', views.summary, name='summary'),
    url(r'^(?P<field>(authors|subjects|journals))/$', views.browse_field, name='browse'),
    url(r'^new/$', views.ingest, name='ingest'),
    url(r'^search/$', views.search, name='search'),
    url(r'^unreviewed/$', views.review_queue, name='review-list'),
    url(r'^departments/$', views.departments, name='list-departments'),
    # we could probably be even more explicit with the pid pattern,
    # but at least require a colon between pidspace and identifier
    url(r'^(?P<pid>[^:]+:[^/]+)/$', views.view_article, name='view'),
    url(r'^(?P<pid>[^:]+:[^/]+)/edit/$', views.edit_metadata, name='edit'),
    url(r'^(?P<pid>[^:]+:[^/]+)/pdf/$', views.download_pdf, name='pdf'),
    # raw datastream view; add other dsids here as appropriate
    url(r'^(?P<pid>[^:]+:[^/]+)/(?P<dsid>contentMetadata|descMetadata|DC|provenanceMetadata)/$',
        views.view_datastream, name='ds'),
    url(r'^(?P<pid>[^:]+:[^/]+)/AUDIT/$', views.audit_trail, name='audit-trail'),
    url(r'^(?P<pid>[^:]+:[^/]+)/(?P<dsid>authorAgreement)/$',
        views.view_private_datastream, name='private_ds'),
    url(r'^(?P<pid>[^:]+:[^/]+)/biblio/$', views.bibliographic_metadata, name='biblio-data'),
    url(r'^(?P<field>[a-zA-Z0-9_-]+)/autocomplete/$', views.suggest, name='suggest'),
    url(r'^journal_publisher/details/$', views.publisher_details, name='publisher-details'),
    url(r'^oa-fund/proposal/$', views.open_access_fund, name='oa-fund-form'),
)
