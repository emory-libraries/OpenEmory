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
from datetime import datetime, date
from django.core.management.base import BaseCommand, CommandError
from optparse import make_option
from time import gmtime, strftime
from django.contrib.auth.models import User
from eulfedora.rdfns import model as relsextns

from rdflib import Namespace, URIRef, Literal
from openemory.common.fedora import ManagementRepository
from openemory.publication.models import Publication, LastRun, ArticleStatistics, year_quarter


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
        
        year = date.today().year
        quarter = year_quarter(date.today().month) #get the quarter 1, 2, 3, 4

        # counters
        self.counts = defaultdict(int)

        # set the name of the report of duplications
        self.reportsdirectory = settings.REPORTS_DIR
        self.reportname = "merge-report-%s.txt" % strftime("%Y-%m-%dT%H-%M-%S")

        # connection to repository
        self.repo = ManagementRepository()


        try:
            #if pids specified, use that list
            if len(args) == 2:
                pids = list(args)
            else:
                raise Exception("specify two pid")
        except Exception as e:
            raise Exception("Error getting pids: %s" % e.message)

        self.counts['total'] = len(pids)

        for idx,pid in enumerate(pids):
            try:
                if idx == 0:
                    self.output(1, "\nProcessing  Elements PID %s" % pid)
                     # Load first as Article becauce that is the most likely type
                    element_obj = self.repo.get_object(pid=pid, type=Publication)
                    element_stats = ArticleStatistics.objects.filter(pid=pid)
                    if element_stats:
                        element_stats.delete()
                    if not element_obj.exists:
                        self.output(1, "Skipping because %s does not exist" % pid)
                        continue
                elif idx == 1:
                    self.output(1, "\nProcessing  Old PID %s" % pid)
                    original_obj = self.repo.get_object(pid=pid, type=Publication)
                    if not original_obj.exists:
                        self.output(1, "Skipping because %s does not exist" % pid)
                        continue
                    original_stats = ArticleStatistics.objects.filter(pid=pid)
                    if not original_stats:
                        original_stats = ArticleStatistics.objects.create(pid=pid, year=year, quarter=quarter)
               
                
                


            except (KeyboardInterrupt, SystemExit):
                if self.counts['saved'] > 0:
                  self.write_report(self.duplicates, error="interrupt")
                raise

            except Exception as e:
                self.output(1, "Error processing %s: %s" % (pid, e.message))
                self.output(1, element_obj.rels_ext.content.serialize(pretty=True))
                self.counts['errors']+=1

        element_obj.descMetadata.content = original_obj.descMetadata.content
        element_obj.provenance.content = original_obj.provenance.content
        element_obj.dc.content = original_obj.dc.content
        if original_obj.pdf.content:
            element_obj.pdf.content = original_obj.pdf.content
        original_obj.state = 'I'
        element_obj.provenance.content.init_object(element_obj.pid, 'pid')
        element_obj.provenance.content.merged(original_obj.pid, element_obj.pid)
        

        for stat in original_stats:
            ArticleStatistics.objects.create(pid=element_obj.pid, year=stat.year, quarter=stat.quarter, num_downloads=stat.num_downloads, num_views=stat.num_views)
        
        coll = self.repo.get_object(pid=settings.PID_ALIASES['oe-collection'])
        element_obj.collection = coll
        element_obj.rels_ext.content.add((element_obj.uriref, relsextns.hasModel, URIRef(Publication.ARTICLE_CONTENT_MODEL)))
        element_obj.rels_ext.content.add((element_obj.uriref, relsextns.hasModel, URIRef(Publication.PUBLICATION_CONTENT_MODEL)))

        
        # SAVE OBJECTS UNLESS NOACT OPTION
        if not options['noact']:
            element_obj.save()
            original_obj.save()
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
