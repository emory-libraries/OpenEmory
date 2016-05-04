from django.conf import settings
from collections import defaultdict
from getpass import getpass
import logging
from optparse import make_option

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.core.paginator import Paginator

from openemory.accounts.models import EsdPerson, UserProfile
from openemory.common import romeo
from openemory.common.fedora import ManagementRepository
from openemory.publication.models import Publication


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    ''' This command run through all the articles and makes sure that journal titles and publishers match against Sherpa Romeo
    '''
    args = "[netid netid ...]"
    help = __doc__

    option_list = BaseCommand.option_list + (
        make_option('--article', '-a',
                    action='store_true',
                    default=False,
                    help='Cleans up content models for articles.'),
        make_option('--book', '-b',
                    action='store',
                    default=False,
                    help='Cleans up content models for books.'),
        make_option('--force', '-f',
                    action='store_true',
                    default=False,
                    help='Updates even if SYMPLECTIC-ATOM has not been modified since last run.'),
        )

    def handle(self, *args, **options):

        self.verbosity = int(options['verbosity'])    # 1 = normal, 0 = minimal, 2 = all
        self.v_normal = 1

        if options['article'] and options['book']:
            raise CommandError('Can not use both parameters')

        if not options['article'] and not options['book']:
            raise CommandError('Use at least one parameter')

        if options['article']:
            cmodel = Publication.ARTICLE_CONTENT_MODEL

        if options['book']:
           cmodel = Publication.BOOK_CONTENT_MODEL

        # connection to repository
        self.repo = ManagementRepository()
        pid_set = self.repo.get_objects_with_cmodel(cmodel, type=Publication)

        try:
            publications = Paginator(pid_set, 100)

        except Exception as e:
            self.output(0, "Error paginating items: : %s " % (e.message))

        #process all Articles
        for p in publications.page_range:
            try:
                objs = publications.page(p).object_list
            except Exception as e:
                #print error and go to next iteration of loop
                self.output(0,"Error getting page: %s : %s " % (p, e.message))
                continue
            for publication in objs:
                try:
                    if not publication.exists:
                        self.output(0, "Skipping %s because pid does not exist" % publication.pid)
                        continue
                    else:
                        if not publication.has_model(Publication.PUBLICATION_CONTENT_MODEL):
                            publication.add_relationship(relsextns.hasModel, Publication.PUBLICATION_CONTENT_MODEL)
                            publication.save()
                    else:
                        continue


                except Exception as e:
                    self.output(0, "Error processing pid: %s : %s " % (article.pid, e.message))
                    # self.counts['errors'] +=1


    def output(self, v, msg):
        '''simple function to handle logging output based on verbosity'''
        if self.verbosity >= v:
            self.stdout.write("%s\n" % msg)