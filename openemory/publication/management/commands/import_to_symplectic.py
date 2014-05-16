#Add to collection file openemory/publication/management/commands/import_to_symplectic.py
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

from time import sleep
import settings
from collections import defaultdict
from getpass import getpass
import logging
from optparse import make_option

from django.core.management.base import BaseCommand, CommandError
from django.core.paginator import Paginator

from eulfedora.server import Repository
from eulxml.xmlmap import load_xmlobject_from_string

from openemory.publication.models import Article, OESympImportArticle, \
    SympDate, SympPerson, SympRelation, SympWarning
from openemory.util import percent_match
import requests

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    '''Fetch article data for `~openemory.publication.models.Article` objects and do the following:
     1. Construct a Symplectic-Elements Article.
     2. PUTs this article to Symplectic-Elements via the API
     If PIDs are provided in the arguments, that list of pids will be used instead of searching fedora.
    '''
    args = "[pid pid ...]"
    help = __doc__

    option_list = BaseCommand.option_list + (
        make_option('--noact', '-n',
                    action='store_true',
                    default=False,
                    help='Reports the pid and total number of Articles that would be processed but does not really do anything.'),
        make_option('--force', '-f',
                    action='store_true',
                    default=False,
                    help='Forces processing by ignoring duplicate detection'),
        make_option('--rel', '-r',
                    action='store_true',
                    default=False,
                    help='Updates author relations even if a record would otherwise be skipped'),
        )

    def handle(self, *args, **options):
        self.verbosity = int(options['verbosity'])    # 1 = normal, 0 = minimal, 2 = all
        self.v_normal = 1

        #counters
        self.counts = defaultdict(int)

        #connection to repository
        repo = Repository(username=settings.FEDORA_MANAGEMENT_USER, password=settings.FEDORA_MANAGEMENT_PASSWORD)

        #Symplectic-Elements setup
        self.session = requests.Session()
        self.session.auth = (settings.SYMPLECTIC_USER, settings.SYMPLECTIC_PASSWORD)
        self.session.verify=False
        self.session.stream=True
        self.session.headers.update({'Content-Type': 'text/xml'})

        self.pub_query_url = "%s/%s" % (settings.SYMPLECTIC_BASE_URL, "publications")
        self.pub_create_url = "%s/%s" % (settings.SYMPLECTIC_BASE_URL, "publication/records/manual")
        self.relation_create_url = "%s/%s" % (settings.SYMPLECTIC_BASE_URL, "relationships")


        #if pids specified, use that list
        try:
            if len(args) != 0:
                pids = list(args)
                pid_set = [repo.get_object(pid=p,type=Article) for p in pids]


            else:
                #search for Articles.
                pid_set = repo.get_objects_with_cmodel(Article.ARTICLE_CONTENT_MODEL, Article)

        except Exception as e:
            raise CommandError('Error getting pid list (%s)' % e.message)

        try:
            articles = Paginator(pid_set, 20)
            self.counts['total'] = articles.count
        except Exception as e:
            self.output(0, "Error paginating items: : %s " % (e.message))

        #process all Articles
        for p in articles.page_range:
            try:
                objs = articles.page(p).object_list
            except Exception as e:
                #print error and go to next iteration of loop
                self.output(0,"Error getting page: %s : %s " % (p, e.message))
                self.counts['errors'] +=1
                continue
            for article in objs:
                try:
                    if not article.exists:
                        self.output(1, "Skipping %s because pid does not exist" % article.pid)
                        self.counts['skipped'] +=1
                        continue
                    title = article.descMetadata.content.title_info.title if (article.descMetadata.content.title_info and article.descMetadata.content.title_info.title) else None
                    if title is None or title == '':
                        self.output(1, "Skipping %s because OE Title does not exist" % (article.pid))
                        self.counts['skipped'] +=1
                        continue

                    if not article.is_published:
                        self.output(1, "Skipping %s because pid is not published" % article.pid)
                        self.counts['skipped'] +=1
                        continue

                    # try to detect article by PMC
                    if article.pmcid and not options['force']:
                        response = self.session.get(self.pub_query_url, params = {'query' : 'external-identifiers.pmc="PMC%s"' % article.pmcid, 'detail': 'full'})
                        entries = load_xmlobject_from_string(response.raw.read(), OESympImportArticle).entries
                        self.output(2, "Query for PMC Match: GET %s %s" % (response.url, response.status_code))
                        if response.status_code == 200:
                            if len(entries) >= 1:
                                self.output(1, "Skipping %s because PMC PMC%s already exists" % (article.pid, article.pmcid))
                                self.counts['skipped'] +=1

                                if options['rel']:
                                    symp_pub, relations = article.as_symp(source=entries[0].source, source_id=entries[0].source_id)
                                    self.process_relations(entries[0].source_id, relations, options)
                                    sleep(1)
                                continue
                        else:
                            self.output(1, "Skipping %s because trouble with request %s %s" % (article.pid, response.status_code, entries[0].title))
                            self.counts['skipped'] +=1
                            continue

                    # try to detect article by Title if it does not have PMC
                    if not options['force']:
                        response = self.session.get(self.pub_query_url, params = {'query' : 'title~"%s"' % title, 'detail': 'full'})
                        entries = load_xmlobject_from_string(response.raw.read(), OESympImportArticle).entries
                        # Accouont for mutiple results
                        titles = [e.title for e in entries]
                        self.output(2, "Query for Title Match: GET %s %s" % (response.url, response.status_code))
                        if response.status_code == 200:
                            found = False
                            for t in titles:
                                success, percent = percent_match(title, t, 90)
                                self.output(1, "Percent Title Match '%s' '%s' %s " % (title, t, percent))
                                if success:
                                    found = True
                            if found:
                                self.output(1, "Skipping %s because Title \"%s\" already exists" % (article.pid, title))
                                self.counts['skipped'] +=1

                                # update relations if rel is set
                                if options['rel']:
                                    symp_pub, relations = article.as_symp(source=entries[0].source, source_id=entries[0].source_id)
                                    self.process_relations(entries[0].source_id, relations, options)
                                    sleep(1)
                                continue
                        else:
                            self.output(1, "Skipping %s because trouble with request %s %s" % (article.pid, response.status_code, entries[0].title))
                            self.counts['skipped'] +=1
                            continue

                    # Process article and relations
                    symp_pub, relations = article.as_symp()
                    self.process_article(article.pid, symp_pub, options)
                    self.process_relations(article.pid, relations, options)
                    sleep(1)

                except Exception as e:
                    self.output(0, "Error processing pid: %s : %s " % (article.pid, e.message))
                    import traceback
                    traceback.print_exc()
                    self.counts['errors'] +=1

        # summarize what was done
        self.stdout.write("\n\n")
        self.stdout.write("Total number selected: %s\n" % self.counts['total'])
        self.stdout.write("Skipped: %s\n" % self.counts['skipped'])
        self.stdout.write("Errors: %s\n" % self.counts['errors'])
        self.stdout.write("Warnings: %s\n" % self.counts['warnings'])
        self.stdout.write("Articles Processed: %s\n" % self.counts['articles_processed'])
        self.stdout.write("Relations Processed: %s\n" % self.counts['relations_processed'])


    def output(self, v, msg):
        '''simple function to handle logging output based on verbosity'''
        if self.verbosity >= v:
            self.stdout.write("%s\n" % msg.encode('utf-8'))


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
            for w in load_xmlobject_from_string(response.raw.read(), OESympImportArticle).warnings:
                self.output(0, 'Warning: %s %s' % (pid, w.message))
                self.counts['warnings']+=1
        self.counts['articles_processed']+=1


    def output(self, v, msg):
        '''simple function to handle logging output based on verbosity'''
        if self.verbosity >= v:
            self.stdout.write("%s\n" % msg.encode('utf-8'))


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
                for w in load_xmlobject_from_string(response.raw.read(), OESympImportArticle).warnings:
                    self.output(0, 'Warning: %s %s' % (pid, w.message))
                    self.counts['warnings']+=1
            except:
                self.output(0,"Trouble reding warnings for relation record in %s" % pid)

        self.counts['relations_processed']+=1