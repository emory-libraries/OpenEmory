from django.contrib.sitemaps import Sitemap
from django.core.urlresolvers import reverse
from eulfedora.server import Repository
from openemory.publication.models import Article
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
        r = solr.query(content_model=Article.ARTICLE_CONTENT_MODEL,
                        state='A')
        return r

    def location(self, article):
        return reverse('publication:view', args=[article['pid']])

    def lastmod(self, article):
        return article['last_modified']
