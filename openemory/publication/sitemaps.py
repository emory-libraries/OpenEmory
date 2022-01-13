# file openemory/publication/sitemaps.py
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

from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from eulfedora.server import Repository
from openemory.publication.models import Publication
from openemory.util import solr_interface


class ArticleSitemap(Sitemap):
    # NOTE: disabling change frequency since it could be highly variable,
    # and we don't want to set something that will keep a search engine
    # from picking up on withdrawn content
    #changefreq = 'yearly'  # mostly archival, so changes should be rare

    # TODO: this should use Solr, and should include article
    # last ate modificationd

    def items(self):
        solr = solr_interface()
        r = solr.query(content_model=Publication.ARTICLE_CONTENT_MODEL,
                        state='A')
        return r

    def location(self, article):
        return reverse('publication:view', args=[article['pid']])

    def lastmod(self, article):
        return article['last_modified']
