from django.contrib.sitemaps import Sitemap
from django.core.urlresolvers import reverse
from eulfedora.server import Repository
from openemory.publication.models import Article

class ArticleSitemap(Sitemap):
    changefreq = 'yearly' # mostly archival, so changes should be rare

    def items(self):
        repo = Repository()
        return repo.get_objects_with_cmodel(Article.ARTICLE_CONTENT_MODEL,
                                            type=Article)

    def location(self, article):
        return reverse('publication:view', args=[article.pid])
