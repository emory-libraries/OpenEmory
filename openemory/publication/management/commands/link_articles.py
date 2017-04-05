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

from rdflib import Namespace, URIRef, Literal

from openemory.common.fedora import ManagementRepository
from openemory.publication.models import Publication, LastRun

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    '''Provides replace/ignore options for duplicate objects created by Elements connector for manual duplicate management.
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
        make_option('--replace', '-r',
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
        self.reportname = "replaces-report-%s.txt" % strftime("%Y-%m-%dT%H-%M-%S")

        # connection to repository
        self.repo = ManagementRepository()

        # get last run time and set new one
        time_zone = pytz.timezone('US/Eastern')

        last_run = LastRun.objects.get(name='Convert Symp to OE')
        date = last_run.start_time

        self.output(1, '%s EST' % date.strftime("%Y-%m-%dT%H:%M:%S"))
        date = time_zone.localize(date)
        date = date.astimezone(pytz.utc)
        date_str = date.strftime("%Y-%m-%dT%H:%M:%S")
        self.output(1, '%s UTC' % date_str)

        try:
            #if pids specified, use that list
            if len(args) != 0:
                pids = list(args)
            else:
                raise Exception("no pids specified")
        except Exception as e:
            raise Exception("Error getting pids: %s" % e.message)

        self.counts['total'] = len(pids)

        try:
            self.output(1, "\nProcessing %s" % pids[0])
            # Load first as Article becauce that is the most likely type
            obj = self.repo.get_object(pid=pids[0])
            if not obj.exists:
                self.output(1, "Skipping because %s does not exist" % pids[0])
                raise Exception("Error getting pids: %s" % e.message)
                # continue

            # choose content type
            content_types = {'Article': 'journal article'}

            obj_types = ds.content.node.xpath('atom:category/@label', namespaces={'atom': 'http://www.w3.org/2005/Atom'})
            if obj_types[1] in content_types.values():
                logging.info("Processing %s as Publication" % pids[0])
                obj = self.repo.get_object(pid=pids[0], type=Publication)
            else:
                logging.info("Skipping %s Invalid Content Type" % pids[0])
                raise Exception("Error getting pids: %s" % e.message)
                # continue

            # Get the pubs object
            # pubs_id = obj.sympAtom.content.serialize().split('<pubs:id>')[1].split('</pubs:id>')[0]
            pubs_id = "pubs:%s" % (pids[1])
            self.output(1, "Pub ID: %s" % pubs_id)
            #ingesting new pubs_id object
            foxml = '<?xml version="1.0" encoding="UTF-8"?>'
                    '<foxml:digitalObject VERSION="1.1" PID="'+ pubs_id +'"'
                    'xmlns:foxml="info:fedora/fedora-system:def/foxml#"'
                    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
                    'xsi:schemaLocation="info:fedora/fedora-system:def/foxml# http://www.fedora.info/definitions/1/0/foxml1-1.xsd">'
                    '<foxml:objectProperties>'
                    '<foxml:property NAME="info:fedora/fedora-system:def/model#state" VALUE="Active"/>'
                    '</foxml:objectProperties>'
                    '</foxml:digitalObject>'
            pubs_obj = self.repo.ingest(text=foxml)
            obj = repo.get_object(pid=pubs_id)
            obj.dc.content.identifier_list.extend(pubs_id)
            original_pid = repo.get_object(pid=pids[0], type=Publication)
            # pubs_dc = '<oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.openarchives.org/OAI/2.0/oai_dc/ http://www.openarchives.org/OAI/2.0/oai_dc.xsd"><dc:identifier>'+ pubs_id +'</dc:identifier></oai_dc:dc>'
            # pubs_obj.dc.content = pubs_dc


            # Update pubs object to point hasCurrent and hasVisible attibutes to the original_pid
            sympns = Namespace('info:symplectic/symplectic-elements:def/model#')
            pubs_obj.rels_ext.content.bind('symp', sympns)
            has_current = (URIRef("info:fedora/"+obj.pid),\
                            URIRef('info:symplectic/symplectic-elements:def/model#hasCurrent'), \
                            URIRef(original_pid))
            has_visible = (URIRef("info:fedora/"+pubs_id),\
                            URIRef('info:symplectic/symplectic-elements:def/model#hasVisible'), \
                            URIRef(original_pid))
            # hasCurrent
            obj.rels_ext.content.set(has_current)

            # hasVisible
            obj.rels_ext.content.set(has_visible)

            # Close pubs rels_ext object
            obj.rels_ext.content.close()

            
            symp_pub, relations = original_pid.as_symp()
            self.process_article(original_pid.pid, symp_pub, options)
            self.process_relations(original_pid.pid, relations, options)

            # SAVE OBJECTS UNLESS NOACT OPTION
            if not options['noact']:
                original_obj.save()
                pubs_obj.save()
                self.counts['saved']+=1



        except (KeyboardInterrupt, SystemExit):
            if self.counts['saved'] > 0:
              self.write_report(self.duplicates, error="interrupt")
            raise

        except Exception as e:
            self.output(1, "Error processing %s: %s" % (pids[0], e.message))
            self.output(1, obj.rels_ext.content.serialize(pretty=True))
            self.counts['errors']+=1

        # summarize what was done
        self.stdout.write("\n\n")
        self.stdout.write("Total number selected: %s\n" % self.counts['total'])
        self.stdout.write("Skipped: %s\n" % self.counts['skipped'])
        self.stdout.write("Errors: %s\n" % self.counts['errors'])
        self.stdout.write("Converted: %s\n" % self.counts['saved'])

        if self.counts['saved'] > 0:
          self.write_report(self.duplicates)

    def write_report(self,duplicates,**kwarg):
        '''write a report listing the pids of the duplicate objects and the \
        corresponding original pids.'''
        try:
          os.mkdir(self.reportsdirectory)
        except Exception:
          pass
        with open(os.path.join(self.reportsdirectory, self.reportname), 'a') as f:
          for pid in duplicates:
            try:
              f.write("Duplicate pid: %s\n" % pids[0])
              f.write("Original pid for duplicate: %s\n\n" % duplicates[pids[0]])
            except:
              self.stdout.write("Something went wrong when writing the report.\n")
          if kwarg and "interrupt" in kwarg['error']:
            f.write("\nReport interrupted at: %s EST" % strftime("%Y-%m-%dT%H:%M:%S"))
          else:
            f.write("\nFinished report at: %s EST" % strftime("%Y-%m-%dT%H:%M:%S"))

    def output(self, v, msg):
        '''simple function to handle logging output based on verbosity'''
        if self.verbosity >= v:

    def process_article(self, pid, symp_pub, options):
        self.output(1,"Processing Article %s" % pid)

        # put article xml
        url = '%s/%s' % (self.pub_create_url, pid)
        status = None
        if symp_pub.is_empty():
            self.output(1,"Skipping becase XML is empty")
            self.counts['skipped']+=1
            return
        valid = symp_pub.is_valid()
        self.output(2,"XML valid: %s" % valid)
        if not valid:
            self.output(0, "Error publication xml is not valid for pid %s %s" % (pid, symp_pub.validation_errors()))
            self.counts['errors']+=1
            return
        if not options['noact']:
            response = self.session.put(url, data=symp_pub.serialize())
            status = response.status_code
        self.output(2,"PUT %s %s" %  (url, status if status else "<NO ACT>"))
        self.output(2, "=====================================================================")
        self.output(2, symp_pub.serialize(pretty=True).decode('utf-8', 'replace'))
        self.output(2,"---------------------------------------------------------------------")
        if status and status not in [200, 201]:
            self.output(0,"Error publication PUT returned code %s for %s" % (status, pid))
            self.counts['errors']+=1
            return
        elif not options['noact']:
            # checkd for warnings
            for w in load_xmlobject_from_string(response.raw.read(), OESympImportPublication).warnings:
                self.output(0, 'Warning: %s %s' % (pid, w.message))
                self.counts['warnings']+=1
        self.counts['articles_processed']+=1


    def process_relations(self, pid, relations, options):

        self.output(1,"Processing Relationss for %s" % pid)

        # put relationship xml
        url = self.relation_create_url
        status= None
        for r in relations:
            self.output(0, "%s %s" % (r.from_object, r.to_object))
            status = None
            valid = r.is_valid()
            self.output(2,"XML valid: %s" % valid)
            if not valid:
                self.output(0, "Error because a relation xml is not valid for pid %s %s" % (pid, r.validation_errors()))
                self.counts['errors']+=1
                continue
            if not options['noact']:
                response = self.session.post(self.relation_create_url, data=r.serialize())
                status = response.status_code

            self.output(2,"POST %s %s" %  (url, status if status else "<NO ACT>"))
            self.output(2,r.serialize(pretty=True))
            self.output(2,"---------------------------------------------------------------------")
        self.output(2,"=====================================================================")
        if status and status not in [200, 201]:
            self.output(0,"Error relation POST returned code %s for %s" % (status, pid))
            self.counts['errors']+=1
            return
        elif not options['noact']:
            # checkd for warnings
            try:
                for w in load_xmlobject_from_string(response.raw.read(), OESympImportPublication).warnings:
                    self.output(0, 'Warning: %s %s' % (pid, w.message))
                    self.counts['warnings']+=1
            except:
                self.output(0,"Trouble reding warnings for relation record in %s" % pid)

        self.counts['relations_processed']+=1