# file openemory/publication/management/commands/add_dc_ident.py
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

from django.conf import settings
from collections import defaultdict
from getpass import getpass
import logging
from optparse import make_option

from django.core.management.base import BaseCommand, CommandError
from django.core.paginator import Paginator

from eulfedora.server import Repository

from openemory.publication.models import Article
from openemory.util import pmc_access_url

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    '''Fetch article data from solr for `~openemory.publication.models.Article` objects and do the following:
     1. Restores dc.identifiers related to PMCID
     2.  Map addition fields to MODS and dc (coming soon)
    '''
    args = "[pid pid ...]"
    help = __doc__

    option_list = BaseCommand.option_list + (
        make_option('--noact', '-n',
                    action='store_true',
                    default=False,
                    help='Reports the pid and total number of Articles that would be processed but does not really do anything.'),
        make_option('--username',
                    action='store',
                    help='Username of fedora user to connect as'),
        make_option('--password',
                    action='store',
                    help='Password for fedora user,  password=  will prompt for password'),
        )


    
    def handle(self, *args, **options):
        self.verbosity = int(options['verbosity'])    # 1 = normal, 0 = minimal, 2 = all
        self.v_normal = 1

        #counters
        counts = defaultdict(int)

        # check required options
        if not options['username']:
            raise CommandError('Username is required')
        else:
            if not options['password'] or options['password'] == '':
                options['password'] = getpass()

        #connection to repository
        repo = Repository(username=options['username'], password=options['password'])



        try:
            #if pids specified, use that list
            if len(args) != 0:
                pids = list(args)
                pid_set = [repo.get_object(pid=p, type=Article) for p in pids]

            else:
                #search for Articles
                pid_set = repo.get_objects_with_cmodel(Article.ARTICLE_CONTENT_MODEL, Article)

        except Exception as e:
            raise CommandError('Error gettings pids (%s)' % e.message)

        try:
            articles = Paginator(pid_set, 20)
            counts['total'] = articles.count
        except Exception as e:
            self.output(0, "Error paginating items: : %s " % (e.message))

        #process all Articles
        for p in articles.page_range:
            try:
                objs = articles.page(p).object_list
            except Exception as e:
                #print error and go to next iteration of loop
                self.output(0,"Error getting page: %s : %s " % (p, e.message))
                counts['errors'] +=1
                continue
            for article in objs:
                try:
                    if not article.exists:
                        self.output(1, "Skipping %s because pid does not exist" % article.pid)
                        counts['skipped'] +=1
                        continue
                    else:
                        self.output(0,"Processing %s" % article.pid)

                        mods = article.descMetadata.content
                        nlm = article.contentMetadata.content if article.contentMetadata.exists else None
                        identifiers = []

                        #PMC info
                        if nlm:
                            pmc = nlm.docid
                            pmc_id = 'PMC%s' % pmc
                            access_url = pmc_access_url(pmc)
                            identifiers.extend([pmc_id, access_url])

                        if mods.ark_uri:
                            identifiers.append(mods.ark_uri)

                        identifiers.append(article.pid)

                        article.dc.content.identifier_list = identifiers

                        ##########REMOVE dc.relation###########
                        #                                     #
                        article.dc.content.relation_list = [] #
                        #                                     #
                        #######################################

                        # save article
                        if not options['noact']:
                            article.save()
                            self.output(1, "SAVED")
                except Exception as e:
                    self.output(0, "Error processing pid: %s : %s " % (article.pid, e.message))
                    counts['errors'] +=1

        # summarize what was done
        self.stdout.write("\n\n")
        self.stdout.write("Total number selected: %s\n" % counts['total'])
        self.stdout.write("Skipped: %s\n" % counts['skipped'])
        self.stdout.write("Errors: %s\n" % counts['errors'])


    def output(self, v, msg):
        '''simple function to handle logging output based on verbosity'''
        if self.verbosity >= v:
            self.stdout.write("%s\n" % msg)
