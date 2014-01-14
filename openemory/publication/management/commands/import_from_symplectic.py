# file openemory/publication/management/commands/import_from_symplectic.py
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

import settings
from collections import defaultdict
from getpass import getpass
import logging
from optparse import make_option

from django.core.management.base import BaseCommand, CommandError
from django.core.paginator import Paginator

from eulfedora.server import Repository

from openemory.publication.models import Article

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    '''Imports articles from Symplectic to OpenEmory in one of two way
    1. Specifying Symplectic id
    2. Querying for all articles in Symplectic that hav not been imported yet
    '''
    args = "[id id ...]"
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
        self.counts = defaultdict(int)

        # check required options
        if not options['username']:
            raise CommandError('Username is required')
        else:
            if not options['password'] or options['password'] == '':
                options['password'] = getpass("Password for %s:" % options['username'])

        #connection to repository
        self.repo = Repository(username=options['username'], password=options['password'])



        try:
            #if ids specified, use that list
            if len(args) != 0:
                ids = list(args)
                #TODO symplectic query here
                for id in ids:
                    self.counts['total']+=1
                    self.output(1, "Processing %s" % id)
                    self.symplectic_to_oe_by_id(id)

            else:
                #search for Articles
                #TODO symplectic query here
                articles = []

        except Exception as e:
            raise CommandError('Error gettings ids (%s)' % e.message)


        # summarize what was done
        self.stdout.write("\n\n")
        self.stdout.write("Total number selected: %s\n" % self.counts['total'])
        self.stdout.write("Skipped: %s\n" % self.counts['skipped'])
        self.stdout.write("Errors: %s\n" % self.counts['errors'])
        self.stdout.write("Created: %s\n" % self.counts['created'])


    def symplectic_to_oe_by_id(self, id):
        #TODO query for article

        # New Article
        article = self.repo.get_object(type=Article)

        # Set to published
        article.state = "A"

        # Title Info
        article.descMetadata.content.create_title_info()
        article.descMetadata.content.title_info.title = "ID %s" % id
        article.label = "ID %s" % id

        # Add to OE Collection
        oe_collection =  repo.get_object(pid=settings.PID_ALIASES['oe-collection'])
        article.collection = oe_collection


        article.descMetadata.content.resource_type = 'text'
        article.descMetadata.content.genre = 'Article'
        


        #article.save()

        print article.descMetadata.content.title_info.title


    def output(self, v, msg):
        '''simple function to handle logging output based on verbosity'''
        if self.verbosity >= v:
            self.stdout.write("%s\n" % msg)
