import logging
from django.core.management.base import BaseCommand
from openemory.harvest.models import OpenEmoryEntrezClient

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    '''Fetch article metadata from PubMed Central, focusing on articles
    affiliated with Emory authors.

    This command connects to PubMed Central via its public web interface and
    finds articles that include Emory in their "Affiliation" metadata.
    '''
    help = __doc__

    def handle(self, *args, **options):
        self.entrez = OpenEmoryEntrezClient()
        results = self.entrez.get_emory_articles()
        print '%d/%d results:' % (len(results.pmid), results.count)
        for id in results.pmid:
            print id
