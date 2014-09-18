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
import logging
from optparse import make_option
from django.core.management.base import BaseCommand, CommandError
from eulfedora.server import Repository
from openemory.publication.models import Article, LastRun
from collections import defaultdict
import pytz
from datetime import datetime


logger = logging.getLogger(__name__)

class Command(BaseCommand):
    '''Finds objects created by Elements connector and converts them to the appropriate OE Content type
    '''
    args = "[pid pid ...]"
    help = __doc__

    option_list = BaseCommand.option_list + (
        make_option('--noact', '-n',
                    action='store_true',
                    default=False,
                    help='Reports the pid and total number of object that would be processed but does not really do anything.'),
        make_option('--date', '-d',
                    action='store',
                    default=False,
                    help='Specify Start Date in format 24-Hour format (YYYY-MM-DDTHH:MM:SS).'),
        )


    
    def handle(self, *args, **options):
        self.options = options
        self.verbosity = int(options['verbosity'])    # 1 = normal, 0 = minimal, 2 = all
        self.v_normal = 1

        #counters
        self.counts = defaultdict(int)

        #connection to repository
        self.repo = Repository(username=settings.FEDORA_MANAGEMENT_USER, password=settings.FEDORA_MANAGEMENT_PASSWORD)

        # get last run time and set new one
        time_zone = pytz.timezone('US/Eastern')

        if not options['date']:
            last_run = LastRun.objects.get(name='Convert Symp to OE')
            date = last_run.start_time
        else:
           try:
               date = datetime.strptime(options['date'], '%Y-%m-%dT%H:%M:%S')
           except:
               raise CommandError("Could not parse date")
        if options['date'] and len(args) !=0:
            raise CommandError('Can not use date option with list of pids')

        if (not options['date']) and  (len(args) == 0) and (not options['noact']):
            last_run.start_time = datetime.now()
            last_run.save()

        self.output(1, '%s EST' % date.strftime("%Y-%m-%dT%H:%M:%S") )
        date = time_zone.localize(date)
        date = date.astimezone(pytz.utc)
        date_str = date.strftime("%Y-%m-%dT%H:%M:%S")
        self.output(1, '%s UTC' % date_str)

        try:
            #if pids specified, use that list
            if len(args) != 0:
                pids = list(args)
            else:
                query = """SELECT ?pid
                        WHERE {
                            ?pid <info:fedora/fedora-system:def/view#disseminates> ?ds.
                             ?pid <info:fedora/fedora-system:def/view#lastModifiedDate> ?modified.
                        FILTER (
                             regex(str(?ds), 'SYMPLECTIC-ATOM') &&
                             ?modified >= xsd:dateTime('%s')
                        )
                        }""" % date_str
                pids = [o['pid'] for o in self.repo.risearch.sparql_query(query)]
        except Exception as e:
            raise Exception("Error getting pids: %s" % e.message)

        self.counts['total'] = len(pids)

        for pid in pids:
            try:
                self.output(1, "Processing %s" % pid)
                # Load first as Article becauce that is the most likely type
                obj = self.repo.get_object(pid=pid)
                if not obj.exists:
                    self.output(1, "Skipping because %s does not exist" % pid)
                    continue
                ds = obj.getDatastreamObject('SYMPLECTIC-ATOM')
                if not ds:
                    self.output(1, "Skipping %s because SYMPLECTIC-ATOM ds does not exist" % pid)
                    continue
                ds_mod = ds.last_modified().strftime("%Y-%m-%dT%H:%M:%S")
                if date_str and  ds_mod < date_str:
                    self.output(1, "Skipping %s because SYMPLECTIC-ATOM ds not modified since last run %s " % (pid, ds_mod))
                    self.counts['skipped']+=1
                    continue

                # WHEN ADDING NEW CONTENT TYPES:
                # 1. Make sure object content modle has from_symp() function
                # 2. Add to  content_types dict
                # 3. Add elif block (see few lines below)
                # 4. Add line in summary section

                #choose content type
                content_types = {'Article': 'journal article'}
                obj_types = ds.content.node.xpath('atom:category/@label', namespaces={'atom': 'http://www.w3.org/2005/Atom'})

                if  content_types['Article'] in obj_types:
                    content_type = 'Article'
                    self.output(1, "Processing %s as Article" % (pid))
                    obj = self.repo.get_object(pid=pid, type=Article)
                #TODO add elif statements for additional contnet types
                else:
                    self.output(1, "Skipping %s because not allowd content type" % (pid))
                    self.counts['skipped']+=1
                    continue

                obj.from_symp()

                if not options['noact']:
                    obj.save()
                    self.counts[content_type]+=1

            except Exception as e:
                self.output(1, "Error processing %s: %s" % (pid, e.message))
                self.counts['errors']+=1

        # summarize what was done
        self.stdout.write("\n\n")
        self.stdout.write("Total number selected: %s\n" % self.counts['total'])
        self.stdout.write("Skipped: %s\n" % self.counts['skipped'])
        self.stdout.write("Errors: %s\n" % self.counts['errors'])
        self.stdout.write("Articles converted: %s\n" % self.counts['Article'])



    def output(self, v, msg):
        '''simple function to handle logging output based on verbosity'''
        if self.verbosity >= v:
            self.stdout.write("%s\n" % msg)
