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
        articles = self.entrez.get_emory_articles()
        for article in articles:
            emails = [ auth.email for auth in article.authors if auth.email ]
            if article.corresponding_author_email and \
                    article.corresponding_author_email not in emails:
                emails.append(article.corresponding_author_email)
            emails_s = (' (%s)' % (', '.join(emails))) if emails else ''
            print '[%s] %s%s' % (article.pmid, article.article_title,
                                 emails_s)
