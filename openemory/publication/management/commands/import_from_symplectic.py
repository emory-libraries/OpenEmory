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

import logging
import sys
import os
import pytz
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from collections import defaultdict
from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from eulfedora.server import Repository
from openemory.publication.models import Publication, LastRun, PublicationPremis
from optparse import make_option
from time import gmtime, strftime
from django.contrib.auth.models import User

logger = logging.getLogger(__name__)
LEVELS = {'debug': logging.DEBUG,
          'info': logging.INFO,
          'warning': logging.WARNING,
          'error': logging.ERROR,
          'critical': logging.CRITICAL}

if len(sys.argv) > 1:
    level_name = sys.argv[1]
    level = LEVELS.get(level_name, logging.NOTSET)
    logging.basicConfig(level=level)

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
        make_option('--force', '-f',
                    action='store_true',
                    default=False,
                    help='Updates even if SYMPLECTIC-ATOM has not been modified since last run.'),
        )

    
    def check_for_duplicates(self,obj):
         # get a list of predicates
        properties = []
        for p in list(obj.rels_ext.content.predicates()):
          properties.append(str(p))
          
        # skip if the rels-ext has the "replaces tag, which indicates duplicates" 
        replaces_tag = "http://purl.org/dc/terms/replaces"
        if replaces_tag in properties:
            self.counts['duplicates']+=1
            # get the pid of the original object this is replaceing
            replaces_pid = obj.rels_ext.content.serialize().split('<dcterms:replaces rdf:resource="')[1].split('"')[0]
            # add to duplicate dict
            self.duplicates[pid.replace('info:fedora/','')] = replaces_pid.replace('info:fedora/','')
            
            
            if not obj.is_withdrawn:

                try:
                    user = User.objects.get(username=u'oebot')
                
                except ObjectDoesNotExist:
                    
                    user = User.objects.get_or_create(username=u'bob', password=u'bobspassword',)[0]
                    user.first_name = "Import"
                    user.last_name = "Process"
                    user.save()
                
                reason = "Duplicate."
                self.counts['withdrawn']+=1
                obj.provenance.content.init_object(obj.pid, 'pid')
                obj.provenance.content.withdrawn(user,reason)
                obj.state = 'I'
                logging.info("Withdrew duplicate pid: %s" % obj.pid)
        


        else:
            self.counts[content_type]+=1

    
    

    def handle(self, *args, **options):
        self.options = options
        self.verbosity = int(options['verbosity'])    # 1 = normal, 0 = minimal, 2 = all
        self.v_normal = 1
        
        #counters
        self.counts = defaultdict(int)

        # duplicates list
        self.duplicates = {}


        # error list
        self.errors = {}

        # set the name of the report of duplications
        self.reportsdirectory = settings.REPORTS_DIR
        self.reportname = "duplicates-report-%s.txt" % strftime("%Y-%m-%dT%H-%M-%S")
        
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

        if (not options['date']) and  (len(args) == 0) and (not options['noact']) and (not options['force']):
            last_run.start_time = datetime.now()
            last_run.save()

        logging.info('%s EST' % date.strftime("%Y-%m-%dT%H:%M:%S"))
        date = time_zone.localize(date)
        date = date.astimezone(pytz.utc)
        date_str = date.strftime("%Y-%m-%dT%H:%M:%S")
        
        logging.info('%s UTC' % date_str)
        try:
            #if pids specified, use that list
            if len(args) != 0:
                pids = list(args)
            else:
                query = """SELECT ?pid
                        WHERE {
                            ?pid <info:fedora/fedora-system:def/view#disseminates> ?ds.
                             ?pid <info:fedora/fedora-system:def/model#createdDate> ?created.
                        FILTER (
                             regex(str(?ds), 'SYMPLECTIC-ATOM') &&
                             ?created >= xsd:dateTime('%sZ')
                        )
                        }""" % date_str
                pids = [o['pid'] for o in self.repo.risearch.sparql_query(query)]
        except Exception as e:
            raise Exception("Error getting pids: %s" % e.message)

        self.counts['total'] = len(pids)

        for pid in pids:
            try:
                logging.info("Processing %s" % pid)
                # Load first as Publication becauce that is the most likely type
                obj = self.repo.get_object(pid=pid)
                if not obj.exists:
                     logging.warning("Skipping because %s does not exist" % pid)

                    continue
                ds = obj.getDatastreamObject('SYMPLECTIC-ATOM')
                if not ds:
                    logging.warning("Skipping %s because SYMPLECTIC-ATOM ds does not exist" % pid)
                    continue
                ds_mod = ds.last_modified().strftime("%Y-%m-%dT%H:%M:%S")
                if date_str and  ds_mod < date_str and (not options['force']):
                    logging.warning("Skipping %s because SYMPLECTIC-ATOM ds not modified since last run %s " % (pid, ds_mod))
                    self.counts['skipped']+=1
                    continue

                # WHEN ADDING NEW CONTENT TYPES:
                # 1. Make sure object content modle has from_symp() function
                # 2. Add to  content_types dict
                # 3. Add elif block (see few lines below)
                # 4. Add line in summary section of this script

                #choose content type
                content_types = {'Article': 'journal article', 'Book': 'book', 'Chapter': 'chapter', 'Conference': 'conference', 'Poster': 'poster', 'Report': 'report'}
                obj_types = ds.content.node.xpath('atom:category/@label', namespaces={'atom': 'http://www.w3.org/2005/Atom'})
                if obj_types[1] in content_types.values():
                    logging.info("Processing %s as Publication" % pid)
                    obj = self.repo.get_object(pid=pid, type=Publication)
                else:
                    logging.info("Skipping %s Invalid Content Type" % pid)
                    continue

                
                obj.from_symp()
                
                check_for_duplicates(obj)
                    

                # convert attached PDF fle to be used with OE
                # filter datastreams for only application/pdf
                mime = None
                mime_ds_list = [i for i in obj.ds_list if obj.ds_list[i].mimeType in obj.allowed_mime_types.values()]

                if mime_ds_list:
                    # sort by DS timestamp does not work yet asks for global name obj because of lambda function
                    new_dict = {}
                    for mime in mime_ds_list:
                        new_dict[mime] = obj.getDatastreamObject(mime).last_modified()

                    sorted_mimes = sorted(new_dict.items(), key=lambda x: x[1])

                    # sorted_mimes = sorted(mime_ds_list, key=lambda p: str(obj.getDatastreamObject(p).last_modified()))
                    mime = sorted_mimes[-1][0]  # most recent
                    


                if not options['noact']:
                    obj.save()

                    if mime:
                        mime_type =  obj.ds_list[mime].mimeType
                        self.repo.api.addDatastream(pid=obj.pid, dsID='content', dsLabel='%s content' % mime_type,
                                                mimeType=mime_type, logMessage='added %s content from %s' % (mime_type,mime),
                                                controlGroup='M', versionable=True, content=obj.getDatastreamObject(mime).content)
                        logging.info("Converting %s to %s Content" % (mime,mime_type)
                        self.counts[mime_type]+=1
                        
            
            except (KeyboardInterrupt, SystemExit):
                if self.counts['duplicates'] > 0:
                  self.write_dup_report(self.duplicates, error="interrupt")
                raise
            
            except Exception as e:
                logging.error("Error processing %s: %s" % (pid, e.message))
                logging.error(obj.rels_ext.content.serialize(pretty=True))
                self.counts['errors']+=1
                self.errors[pid] = e.message

        # summarize what was done
        self.stdout.write("\n\n")
        self.stdout.write("Total number selected: %s\n" % self.counts['total'])
        self.stdout.write("Skipped: %s\n" % self.counts['skipped'])
        self.stdout.write("Duplicates: %s\n" % self.counts['duplicates'])
        self.stdout.write("Withdrew: %s\n" % self.counts['withdrawn'])
        self.stdout.write("PDFs converted: %s\n" % self.counts['pdf'])
        self.stdout.write("Errors: %s\n" % self.counts['errors'])
        self.stdout.write("Publications converted: %s\n" % self.counts['Article'])
        
        if self.counts['duplicates'] > 0 or self.counts['errors'] > 0:
          self.write_dup_report(self.duplicates, self.errors)

    def write_dup_report(self, duplicates, errors, **kwarg):
        '''write a report listing the pids of the duplicate objects and the \
        corresponding original pids.'''
        try:
          os.mkdir(self.reportsdirectory)
        except Exception:
          pass
        with open(os.path.join(self.reportsdirectory, self.reportname), 'a') as f:
          for pid in duplicates:
            try:
              f.write("Duplicate pid: %s\n" % pid)
              f.write("Original pid for duplicate: %s\n\n" % duplicates[pid])
            except:
              self.stdout.write("Something went wrong when writing the report.\n")
          for pid in errors:
            try:
              f.write("Error: %s - %s" % (pid, errors[pid]))
            except:
              self.stdout.write("Something went wrong when writing the report.\n")
          if kwarg and "interrupt" in kwarg['error']:
            f.write("\nReport interrupted at: %s EST" % strftime("%Y-%m-%dT%H:%M:%S"))
          else:
            f.write("\nFinished report at: %s EST" % strftime("%Y-%m-%dT%H:%M:%S"))

    def output(self, v, msg):
        '''simple function to handle logging output based on verbosity'''
        if self.verbosity >= v:
            self.stdout.write("%s\n" % msg)
