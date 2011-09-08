import logging
from collections import defaultdict
from django.core.management.base import BaseCommand
from eulxml import xmlmap
from openemory.harvest.entrez import EFetchResponse
from openemory.harvest.models import OpenEmoryEntrezClient, HarvestRecord
from optparse import make_option
from os import path

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    '''Fetch article metadata from PubMed Central, focusing on articles
    affiliated with Emory authors.

    This command connects to PubMed Central via its public web interface and
    finds articles that include Emory in their "Affiliation" metadata.
    '''
    help = __doc__

    FETCH_ARTICLE_COUNT = 20 # TODO: make this an option

    option_list = BaseCommand.option_list + (
        make_option('--simulate',
                    action='store_true',
                    dest='simulate',
                    default=False,
                    help='Simulate querying for articles ' +
                    '(use local static fixture response for testing/development)'),
        )
    
    def handle(self, *args, **options):
        self.verbosity = int(options['verbosity'])    # 1 = normal, 0 = minimal, 2 = all
        self.v_normal = 1

        if 'simulate' in options and options['simulate']:
            # simulation mode requested; load fixture response
            articles = self.simulated_response()
            if self.verbosity >= self.v_normal:
                self.stdout.write('Simulation mode requested; using static fixture content\n')
        else:
            self.entrez = OpenEmoryEntrezClient()
            article_qs = self.entrez.get_emory_articles() 
            articles = article_qs[:20]

        stats = defaultdict(int)            
        for article in articles:
            stats['articles'] += 1

            if self.verbosity > self.v_normal:
                self.stdout.write('Processing [%s] "%s"\n' % \
                                  (article.docid, article.article_title))
            
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



    def simulated_response(self):
        article_path = path.join(path.dirname(__file__), '..',
            '..', 'fixtures', 'efetch-retrieval-from-hist.xml')
        fetch_response = xmlmap.load_xmlobject_from_file(article_path,
                                                         xmlclass=EFetchResponse)
        return fetch_response.articles
