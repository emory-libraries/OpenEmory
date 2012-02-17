from datetime import date
from django.db.models import Sum
from openemory.publication.forms import BasicSearchForm
from openemory.publication.models import Article, ArticleStatistics
from openemory.util import solr_interface

def search_form(request):
    '''`Template context processor
    <https://docs.djangoproject.com/en/dev/ref/settings/#template-context-processors>`_
    to add a :class:`~openemory.publication.forms.BasicSearchForm` named
    ``ARTICLE_SEARCH_FORM`` to each page.'''
    return { 'ARTICLE_SEARCH_FORM': BasicSearchForm(auto_id='search-%s') }


def statistics(request):
    '''`Template context processor
    <https://docs.djangoproject.com/en/dev/ref/settings/#template-context-processors>`_
    to add publication statistics to page context under the name
    ARTICLE_STATISTICS. The object has five properties: ``total_articles``,
    ``year_views``, ``year_downloads``, ``total_views``, and
    ``total_downloads``.'''

    solr_query = solr_interface().query() \
                                 .filter(content_model=Article.ARTICLE_CONTENT_MODEL,
                                         state='A') \
                                 .paginate(rows=0)
    article_count = solr_query.execute().numFound
    stats = dict(total_articles=article_count)

    total_qs = ArticleStatistics.objects.all()
    total_stats = total_qs.aggregate(total_views=Sum('num_views'),
                                     total_downloads=Sum('num_downloads'))
    stats.update(total_stats)
    
    year_qs = ArticleStatistics.objects.filter(year=date.today().year)
    year_stats = year_qs.aggregate(year_views=Sum('num_views'),
                                   year_downloads=Sum('num_downloads'))
    stats.update(year_stats)

    return { 'ARTICLE_STATISTICS': stats }
