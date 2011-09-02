import logging
from django.core.management.base import BaseCommand
from openemory.harvest.entrez import EntrezClient

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    '''Fetch article metadata from PubMed Central, focusing on articles
    affiliated with Emory authors.

    This command connects to PubMed Central via its public web interface and
    finds articles that include Emory in their "Affiliation" metadata.
    '''
    help = __doc__

    ENTREZ_ROOT = 'http://eutils.ncbi.nlm.nih.gov/entrez/eutils/'
    ESEARCH = ENTREZ_ROOT + 'esearch.fcgi?'

    def handle(self, *args, **options):
        self.entrez = EntrezClient()
        results = self.get_initial_search_results()
        print '%d/%d results:' % (len(results.pmid), results.count)
        for id in results.pmid:
            print id

    def get_initial_search_results(self):
        return self.entrez.esearch(
                db='pmc',     # search PubMed Central
                term='emory', # for the term "emory"
                field='affl', # in the "Affiliation" field
            )
