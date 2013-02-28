# file openemory/publication/context_processors.py
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
    article_count = solr_query.execute().result.numFound
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
