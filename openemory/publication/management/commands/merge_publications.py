# file openemory/publication/management/commands/handle_duplicates_from_symplectic.py
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

import logging
import os
import pytz
from django.conf import settings

from collections import defaultdict
from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from optparse import make_option
from time import gmtime, strftime
from django.contrib.auth.models import User
from eulfedora.rdfns import model as relsextns

from rdflib import Namespace, URIRef, Literal

from openemory.common.fedora import ManagementRepository
from openemory.publication.models import Publication, LastRun, ArticleStatistics

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    '''Provides merge/ignore options for duplicate objects created by Elements connector for manual duplicate management.
        This alters the pubs_object that the original and duplicate share.
    '''
    args = "[pid pid ...]"
    help = __doc__

    option_list = BaseCommand.option_list + (
        make_option('--noact', '-n',
                    action='store_true',
                    default=False,
                    help='Reports the pid and total number of object that would be processed but does not really do anything.'),
        make_option('--ignore', '-i',
                    action='store_true',
                    default=False,
                    help='Changes the pub object to disregard the duplicate pids.'),
        make_option('--merge', '-m',
                    action='store_true',
                    default=False,
                    help='Keeps the changes from the duplicate pids by copying ATOM-FEED to original.'),
        )

    def handle(self, *args, **options):
        


        self.options = options
        self.verbosity = int(options['verbosity'])    # 1 = normal, 0 = minimal, 2 = all
        self.v_normal = 1
        

        # counters
        self.counts = defaultdict(int)

        # duplicates list
        self.duplicates = {}

        # set the name of the report of duplications
        self.reportsdirectory = settings.REPORTS_DIR
        self.reportname = "merge-report-%s.txt" % strftime("%Y-%m-%dT%H-%M-%S")

        # connection to repository
        self.repo = ManagementRepository()

        # get last run time and set new one
        time_zone = pytz.timezone('US/Eastern')

        last_run = LastRun.objects.get(name='Merge Symp with OE')
        date = last_run.start_time

        self.output(1, '%s EST' % date.strftime("%Y-%m-%dT%H:%M:%S"))
        date = time_zone.localize(date)
        date = date.astimezone(pytz.utc)
        date_str = date.strftime("%Y-%m-%dT%H:%M:%S")
        self.output(1, '%s UTC' % date_str)


        try:
            # Raise error if replace or ignore is not specified
            if self.options['merge'] is self.options['ignore']:
                raise Exception("no actions set. Specify --merge or --ignore")

            #if pids specified, use that list
            if len(args) == 2:
                pids = list(args)
            else:
                raise Exception("specify two pid")
        except Exception as e:
            raise Exception("Error getting pids: %s" % e.message)

        self.counts['total'] = len(pids)

        for idx,pid in pids:
            try:
                if idx == 0:
                    self.output(1, "\nProcessing  Elements PID %s" % pid)
                     # Load first as Article becauce that is the most likely type
                    element_obj = self.repo.get_object(pid=pid, type=Publication)
                    new_stats = ArticleStatistics.objects.get_or_create(pid=pid)
                    if not element_obj.exists:
                        self.output(1, "Skipping because %s does not exist" % pid)
                        continue

                elif idx == 1:
                    self.output(1, "\nProcessing  Old PID %s" % pid)
                    original_obj = self.repo.get_object(pid=pid, type=Publication)
                    original_stats = ArticleStatistics.objects.get_or_create(pid=pid)
                    if not original_obj.exists:
                        self.output(1, "Skipping because %s does not exist" % pid)
                        continue
               
                
                


            except (KeyboardInterrupt, SystemExit):
                if self.counts['saved'] > 0:
                  self.write_report(self.duplicates, error="interrupt")
                raise

            except Exception as e:
                self.output(1, "Error processing %s: %s" % (pid, e.message))
                self.output(1, element_obj.rels_ext.content.serialize(pretty=True))
                self.counts['errors']+=1

        element_obj.descMetadata = original_obj.descMetadata
        element_obj.provenance = original_obj.provenance
        element_obj.dc = original_obj.dc

        new_stats.year = original_stats.year
        new_stats.quarter = original_stats.quarter
        new_stats.num_views = original_stats.num_views
        new_stats.num_downloads = original_stats.num_downloads
        new_stats.save()
        
        coll = self.repo.get_object(pid=settings.PID_ALIASES['oe-collection'])
        element_obj.collection = coll
        element_obj.rels_ext.content.add((element_obj.uriref, relsextns.hasModel, URIRef(Publication.ARTICLE_CONTENT_MODEL)))
        element_obj.rels_ext.content.add((element_obj.uriref, relsextns.hasModel, URIRef(Publication.PUBLICATION_CONTENT_MODEL)))

        
        # SAVE OBJECTS UNLESS NOACT OPTION
        if not options['noact']:
            element_obj.save()
            self.counts['saved']+=1

        # summarize what was done
        self.stdout.write("\n\n")
        self.stdout.write("Total number selected: %s\n" % self.counts['total'])
        self.stdout.write("Skipped: %s\n" % self.counts['skipped'])
        self.stdout.write("Errors: %s\n" % self.counts['errors'])
        self.stdout.write("Converted: %s\n" % self.counts['saved'])


    def output(self, v, msg):
        '''simple function to handle logging output based on verbosity'''
        if self.verbosity >= v:
            self.stdout.write("%s\n" % msg)
