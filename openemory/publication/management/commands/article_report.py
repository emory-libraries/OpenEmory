#Add to collection file openemory/publication/management/commands/add_to_oai.py
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
from openemory.accounts.models import EsdPerson, UserProfile
from django.contrib.auth.models import User
import csv

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    '''Fetch article data from fedora for `~openemory.publication.models.Article` objects and has options to do the following:
     1. Count articles by division.
     2. Couonts articles by author
     3. Couonts articles by lead author (first author)
    '''
    help = __doc__

    option_list = BaseCommand.option_list + (
        make_option('--username',
                    action='store',
                    help='Username of fedora user to connect as'),
        make_option('--password',
                    action='store',
                    help='Password for fedora user,  password=  will prompt for password'),
        make_option('-d',
                    dest='div',
                    action='store_true',
                    help='Will run the count by division report'),
        make_option('-a',
                    dest='author',
                    action='store_true',
                    help='Will run the count by division report'),
        make_option('-l',
                    dest='lead',
                    action='store_true',
                    help='Will run the count by division but only taking into account the lead Emory author')
        )


    counts = defaultdict(int)
    div_counts = defaultdict(int)
    author_counts = defaultdict(int)
    lead_counts = defaultdict(int)

    def handle(self, *args, **options):
        self.verbosity = int(options['verbosity'])    # 1 = normal, 0 = minimal, 2 = all
        self.v_normal = 1



        # check required options
        if (not options['div']) and (not options['author']) and (not options['lead']):
            raise CommandError('At least one of the options div, author or lead is required')
        if not options['username']:
            raise CommandError('Username is required')
        else:
            if not options['password'] or options['password'] == '':
                options['password'] = getpass()

        #connection to repository
        repo = Repository(username=options['username'], password=options['password'])
        pid_set = repo.get_objects_with_cmodel(Article.ARTICLE_CONTENT_MODEL, Article)

        try:
            articles = Paginator(pid_set, 100)
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
                        self.output(0, "Skipping %s because pid does not exist" % article.pid)
                        self.counts['skipped'] +=1
                        continue
                    else:
                        self.output(2,"Processing %s" % article.pid)
                        if options['div']:
                            self.division(article)
                        if options['author']:
                            self.author(article)
                        if options['lead']:
                            self.lead(article)
                except Exception as e:
                    self.output(0, "Error processing pid: %s : %s " % (article.pid, e.message))
                    self.counts['errors'] +=1

        # write files
        if options['div']:
            writer = csv.writer(open("division_report.csv", 'w'))
            writer.writerow(['Division', 'Count'])
            for key, count in self.div_counts.items():
                writer.writerow([key, count])

        if options['author']:
            writer = csv.writer(open("author_report.csv", 'w'))
            writer.writerow(['Author', 'Division', 'Department', 'Count'])
            for netid, count in self.author_counts.items():
                try:
                    person = User.objects.get(username=netid).get_profile().esd_data()
                    writer.writerow([person.directory_name, person.division_name, person.department_shortname, count])
                except (User.DoesNotExist, UserProfile.DoesNotExist, EsdPerson.DoesNotExist) as e :
                    self.output(0, "At least one part (User, Profile, ESD) for netid  %s could not be found" % netid)

        if options['lead']:
            writer = csv.writer(open("lead_report.csv", 'w'))
            writer.writerow(['Division', 'Count'])
            for key, count in self.lead_counts.items():
                writer.writerow([key, count])

        # summarize what was done
        self.stdout.write("\n\n")
        self.stdout.write("Total number selected: %s\n" % self.counts['total'])
        self.stdout.write("Skipped: %s\n" % self.counts['skipped'])
        self.stdout.write("Errors: %s\n" % self.counts['errors'])


    def division(self, article):
        self.output(1, "Checking Division Stats for %s" % article.pid)
        esd_info = article.author_esd
        divs = set()
        for e in esd_info:
            divs.add(e.division_name)

        for d in divs:
            self.div_counts[d]+=1


    def author(self, article):
        self.output(1, "Checking Author Stats for %s" % article.pid)
        netids = article.author_netids
        authors = set()
        authors.update(netids)

        for a in authors:
            self.author_counts[a]+=1

    def lead(self, article):
        self.output(1, "Checking Lead Author Stats for %s" % article.pid)
        esd_info = article.author_esd
        if esd_info:
            l = esd_info[0]
            self.lead_counts[l.division_name]+=1


    def output(self, v, msg):
        '''simple function to handle logging output based on verbosity'''
        if self.verbosity >= v:
            self.stdout.write("%s\n" % msg)