# file openemory/publication/management/commands/cleanup_articles.py
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
from getpass import getpass
import logging
from optparse import make_option
from django.core.management.base import BaseCommand, CommandError
from eulfedora.server import Repository
from openemory.publication.models import Article

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    '''Fetches `~openemory.publication.models.Article` objects from Fedora and fixes the DC and MODS checksumes:
     1. Replaces '\r' with '' in abstract field.
     2. Save object. Note: this will make a new version of the mods and copy some fields to the DC
     If PIDs are provided in the arguments, that list of pids will be used instead of searching Fedora.
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
        self.repo = Repository(username=options['username'], password=options['password'])


        #if pids specified, use that list
        if len(args) != 0:
            article_set = self.get_pids(args)

        else:
            #search for Articles in Fedora.
            article_set = self.repo.get_objects_with_cmodel(Article.ARTICLE_CONTENT_MODEL, type=Article)

        #counts['total'] = article_set.count

#        self.stdout.write(article_set)
        #process all Articles
        for a in article_set:
            self.output(1, "Processing %s" % a.pid)


            self.stdout.write('%s %s %s\n' % (a.descMetadata.content.abstract is not None, len(a.descMetadata.content.abstract.text), a.dc.validate_checksum()))
            if (a.descMetadata.content.abstract is not None) and (a.descMetadata.content.abstract.text) and (not a.dc.validate_checksum()):
                a.descMetadata.content.abstract.text = a.descMetadata.content.abstract.text.replace('\r', '')
                # save article
                try:
                    if not options['noact']:
                        a.save("Removing \r to fix checksums")
                except Exception as e:
                    self.output(0, "Error processing pid: %s : %s " % (a.pid, e.message))
                    counts['errors'] +=1
                counts['fixed'] +=1
            else:
                self.output(1, "Skipping %s" % a.pid)
                counts['skip']+=1


        # summarize what was done
        self.stdout.write("\n\n")
        self.stdout.write("Fixed: %s\n" % counts['fixed'])
        self.stdout.write("Skipped: %s\n" % counts['skip'])
        self.stdout.write("Errors: %s\n" % counts['errors'])



    def get_pids(self, pids):
        # get objects only if they are Articles
        # Return generator
        for p in pids:
            obj = self.repo.get_object(pid=p, type=Article)
            if str(obj.get_models()[0]) == Article.ARTICLE_CONTENT_MODEL:
                yield obj


    def output(self, v, msg):
        '''simple function to handle logging output based on verbosity'''
        if self.verbosity >= v:
            self.stdout.write("%s\n" % msg)
