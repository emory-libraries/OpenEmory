from django.conf import settings
from collections import defaultdict
from getpass import getpass
import logging
from optparse import make_option

from django.core.management.base import BaseCommand, CommandError
from django.core.paginator import Paginator

from eulfedora.server import Repository

from openemory.publication.models import Article
from openemory.accounts.models import EsdPerson, UserProfile
from django.contrib.auth.models import User
from openemory.common import romeo

def journal_suggestion_data(journal):
    return {
        'label': '%s (%s)' %
            (journal.title, journal.publisher_romeo or
                            'unknown publisher'),
        'value': journal.title,
        'issn': journal.issn,
        'publisher': journal.publisher_romeo,
    }

def publisher_suggestion_data(publisher):
    return {
        'label': ('%s (%s)' % (publisher.name, publisher.alias))
                 if publisher.alias else
                 publisher.name,
        'value': publisher.name,
        'romeo_id': publisher.id,
        'preprint': {
                'archiving': publisher.preprint_archiving,
                'restrictions': [unicode(r)
                                 for r in publisher.preprint_restrictions],
            },
        'postprint': {
                'archiving': publisher.postprint_archiving,
                'restrictions': [unicode(r)
                                 for r in publisher.postprint_restrictions],
            },
        'pdf': {
                'archiving': publisher.pdf_archiving,
                'restrictions': [unicode(r)
                                 for r in publisher.pdf_restrictions],
            },
        }



logger = logging.getLogger(__name__)

class Command(BaseCommand):
    ''' This command run through all the articles and makes sure that journal titles and publishers match against Sherpa Romeo
    '''
    args = "[netid netid ...]"
    help = __doc__

    option_list = BaseCommand.option_list + (
        make_option('--noact', '-n',
                    action='store_true',
                    default=False,
                    help='Fixed all caps title in articles'),
        )

    def handle(self, *args, **options):

        self.verbosity = int(options['verbosity'])    # 1 = normal, 0 = minimal, 2 = all
        self.v_normal = 1

        #connection to repository
        repo = Repository(username="fedoraAdmin", password="fedoraAdmin")
        pid_set = repo.get_objects_with_cmodel(Article.ARTICLE_CONTENT_MODEL, Article)


        try:
            articles = Paginator(pid_set, 100)

        except Exception as e:
            self.output(0, "Error paginating items: : %s " % (e.message))

        #process all Articles
        for p in articles.page_range:
            try:
                objs = articles.page(p).object_list
            except Exception as e:
                #print error and go to next iteration of loop
                self.output(0,"Error getting page: %s : %s " % (p, e.message))
                continue
            for article in objs:
                try:
                    if not article.exists:
                        self.output(0, "Skipping %s because pid does not exist" % article.pid)
                        continue
                    else:
                        mods = article.descMetadata.content
                        if mods.journal is not None:
                            if mods.journal.title is not None:
                                try:
                                    journals = romeo.search_journal_title(mods.journal.title, type='starts') if mods.journal.title else []
                                    suggestions = [journal_suggestion_data(journal) for journal in journals]
                                    mods.journal.title = suggestions[0]['value']
                                    print mods.journal.title
                                except:
                                    suggestions = []
                                
                            if mods.journal.publisher is not None:
                                try:
                                    publishers = romeo.search_publisher_name(mods.journal.publisher, versions='all')
                                    suggestions = [publisher_suggestion_data(pub) for pub in publishers]
                                    mods.journal.publisher = suggestions[0]['value']
                                    print mods.journal.publisher
                                except:
                                    suggestions = []
                            article.save()
                        else:
                            continue

                        
                except Exception as e:
                    self.output(0, "Error processing pid: %s : %s " % (article.pid, e.message))
                    # self.counts['errors'] +=1


    def output(self, v, msg):
        '''simple function to handle logging output based on verbosity'''
        if self.verbosity >= v:
            self.stdout.write("%s\n" % msg)