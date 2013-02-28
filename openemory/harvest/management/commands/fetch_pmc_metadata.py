# file openemory/harvest/management/commands/fetch_pmc_metadata.py
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

from collections import defaultdict
import logging
from optparse import make_option
import os

from django.core.management.base import BaseCommand
from django.core.paginator import Paginator
from eulxml import xmlmap

from openemory.harvest.entrez import EFetchResponse
from openemory.harvest.models import OpenEmoryEntrezClient, HarvestRecord

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    '''Fetch article metadata from PubMed Central, focusing on articles
    affiliated with Emory authors.

    This command connects to PubMed Central via its public web interface and
    finds articles that include Emory in their "Affiliation" metadata.
    '''
    help = __doc__

    option_list = BaseCommand.option_list + (
        make_option('--simulate', '-n',
                    action='store_true',
                    default=False,
                    help='Simulate querying for articles ' +
                    '(use local static fixture response for testing/development)'),
        make_option('--count', '-c',
                    type='int',
                    default=20,
                    help='Number of articles to fetch at a time.'),
        )
    
    def handle(self, *args, **options):
        self.verbosity = int(options['verbosity'])    # 1 = normal, 0 = minimal, 2 = all
        self.v_normal = 1

        stats = defaultdict(int)
        for article_chunk in self.article_chunks(**options):
            if self.verbosity > self.v_normal:
                self.stdout.write('Starting article chunk.\n')

            for article in article_chunk:
                stats['articles'] += 1

                if self.verbosity > self.v_normal:
                    # python2.6 fails with ascii encoding errors (on unicode
                    # titles) unless we explicitly encode output to
                    # sys.stdout.write
                    msg = u'Processing [%s] "%s"\n' % \
                          (article.docid, article.article_title)
                    self.stdout.write(msg.encode(self.stdout.encoding))
                
                if HarvestRecord.objects.filter(pmcid=article.docid).exists():
                    if self.verbosity >= self.v_normal:
                        self.stdout.write('[%s] has already been harvested; skipping\n' \
                                          % (article.docid,))
                    continue
                    
                if article.identifiable_authors():
                    try:
                        HarvestRecord.init_from_fetched_article(article)
                        stats['harvested'] += 1
                    except Exception as err:
                        self.stdout.write('Error creating record from article: %s\n' % err)
                        stats['errors'] += 1
                        
                else:
                    if self.verbosity >= self.v_normal:
                        self.stdout.write('[%s] has no identifiable authors; skipping\n' \
                                          % (article.docid,))
                    stats['noauthor'] += 1

            # if we haven't gotten any articles yet, keep going. if we have,
            # then we're done.
            if stats['harvested']:
                if self.verbosity > self.v_normal:
                    self.stdout.write('Harvested articles; stopping.')
                break

        else:
            if self.verbosity > self.v_normal:
                self.stdout.write('Processed all chunks.')
            

        # summarize what was done
        if self.verbosity >= self.v_normal:
            self.stdout.write('\nArticles processed: %(articles)d\n' % stats)
            if stats['harvested']:
                self.stdout.write('Articles harvested: %(harvested)d\n' % stats)
            if stats['errors']:
                self.stdout.write('Errors harvesting articles: %(errors)d\n' % stats)
            if stats['noauthor']:
                self.stdout.write('Articles skipped (no identifiable authors): %(noauthor)d\n' \
                                  % stats)

    def article_chunks(self, simulate, count, **kwargs):
        if simulate:
            # simulation mode requested; load fixture response
            if self.verbosity >= self.v_normal:
                self.stdout.write('Simulation mode requested; using static fixture content\n')
            yield self.simulated_response()
        else:
            entrez = OpenEmoryEntrezClient()
            qs = entrez.get_emory_articles() 
            paginator = Paginator(qs, count)
            for i in paginator.page_range:
                page = paginator.page(i)
                yield page.object_list
        

    def simulated_response(self):
        article_path = os.path.join(os.path.dirname(__file__), '..',
            '..', 'fixtures', 'efetch-retrieval-from-hist.xml')
        fetch_response = xmlmap.load_xmlobject_from_file(article_path,
                                                         xmlclass=EFetchResponse)
        return fetch_response.articles
