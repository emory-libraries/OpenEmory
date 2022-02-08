# file openemory/urls.py
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

from django.conf import settings
from django.conf.urls import include, url
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap, index
from django.views.static import serve
from django.views.generic import TemplateView
from django.contrib.flatpages.sitemaps import FlatPageSitemap
from django.views.generic.base import RedirectView

from openemory.accounts.sitemaps import ProfileSitemap
from openemory.publication.sitemaps import ArticleSitemap
from openemory.publication.views import site_index
from openemory.accounts.views import feedback

admin.autodiscover()

urlpatterns = [
    url(r'^$', site_index,  name='site-index'),
    url('^feedback/$', feedback, name='feedback'),
    url(r'^publications/', include(('openemory.publication.urls', 'publication'), namespace='publication')),
    url(r'^harvest/', include(('openemory.harvest.urls', 'harvest'), namespace='harvest')),
    # django db admin
    url(r'^db-admin/doc/', include('django.contrib.admindocs.urls')),
    url(r'^db-admin/', admin.site.urls),
    # indexdata
    url(r'^indexdata/', include(('eulfedora.indexdata.urls', 'indexdata'), namespace='indexdata')),
    # accounts app includes several top-level urls
    url(r'^', include(('openemory.accounts.urls', 'accounts'), namespace='accounts')),
    url(r'^robots.txt$', TemplateView.as_view(template_name='robots.txt',content_type='text/plain')),
    url(r'^oa-fund/authors/$', RedirectView.as_view(url='http://sco.library.emory.edu/open-access-publishing/oa-funding-support/index.html', permanent=False), name='fund-authors'),
    url(r'^authors/oa-fund/$', RedirectView.as_view(url='http://sco.library.emory.edu/open-access-publishing/oa-funding-support/index.html', permanent=False), name='fund-authors'),
    url(r'^publishing-your-data/$', RedirectView.as_view(url='http://sco.library.emory.edu/research-data-management/publishing/', permanent=False), name='publishing_your_data'),
]

# xml sitemaps for search-engine discovere
sitemaps = {
    'articles': ArticleSitemap,
    'profiles': ProfileSitemap,
    'flatpages': FlatPageSitemap,
}
urlpatterns += [
    url(r'^sitemap-(?P<section>.+)\.xml$', sitemap, {'sitemaps': sitemaps},
        name='django.contrib.sitemaps.views.sitemap'),
    url(r'^sitemap\.xml$', index, {'sitemaps': sitemaps},
        name='django.contrib.sitemaps.views.index'),
]

if settings.DEBUG:
    urlpatterns += [
        url(r'^media/(?P<path>.*)$', serve, {
            'document_root': settings.MEDIA_ROOT,
        }),
    ]
