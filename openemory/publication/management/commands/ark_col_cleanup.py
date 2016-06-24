from django.conf import settings
from collections import defaultdict
from getpass import getpass
import logging
from optparse import make_option

from django.core.management.base import BaseCommand, CommandError
from django.core.paginator import Paginator

from eulfedora.server import Repository

from openemory.publication.models import Publication
from openemory.accounts.models import EsdPerson, UserProfile
from django.contrib.auth.models import User
from openemory.common import romeo
from django.utils.encoding import smart_str
import csv

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
        self.repo = Repository(settings.FEDORA_ROOT, username=settings.FEDORA_MANAGEMENT_USER, password=settings.FEDORA_PASSWORD)
        pid_set = self.repo.get_objects_with_cmodel(Publication.ARTICLE_CONTENT_MODEL, type=Publication)
        coll =  self.repo.get_object(pid=settings.PID_ALIASES['oe-collection'])
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
                        
                        print coll
                        print article.pid
                        article.collection = coll
                        ark_uri = '%sark:/25593/%s' % (settings.PIDMAN_HOST, article.pid.split(':')[1])
                        article.dc.content.identifier_list.extend([ark_uri])
                        article.save()
        
                except Exception as e:
                    self.output(0, "Error processing pid: %s : %s " % (article.pid, e.message))
                    # self.counts['errors'] +=1


    def output(self, v, msg):
        '''simple function to handle logging output based on verbosity'''
        if self.verbosity >= v:
            self.stdout.write("%s\n" % msg)