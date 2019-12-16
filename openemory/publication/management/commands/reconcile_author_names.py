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
from openemory.accounts.models import EsdPerson, UserProfile
from rdflib import Namespace, URIRef, Literal
from openemory.common.fedora import ManagementRepository
from openemory.publication.models import Publication, LastRun, ArticleStatistics, year_quarter


logger = logging.getLogger(__name__)

class Command(BaseCommand):
    '''Reconciles EmoryFirst Names and ESD names for each author of the article
        
    '''
    help = __doc__

    

    def handle(self, *args, **options):

        # set the name of the report of duplications
        self.reportsdirectory = settings.REPORTS_DIR
        
        # connection to repository
        self.repo = ManagementRepository()
        solr = solr_interface()
        netid_set = solr.query().filter(content_model=Publication.ARTICLE_CONTENT_MODEL,state='A').\
                facet_by('owner').paginate(rows=0).execute()
        
        netid_set = netid_set.facet_counts.facet_fields['owner']
        netid_set = [n[0] for n in netid_set]
        
        users = User.objects.all()

        for u in users:
            if u.userprofile.has_profile_page():
                profile = u.userprofile
                esd = EsdPerson.objects.get(netid=u.username.upper())
            try:
                article_query = solr.query().filter(content_model=Publication.ARTICLE_CONTENT_MODEL,state='A' ,
                                                 owner=n).field_limit(['pid', 'title'])
                articles = Paginator(article_query, 5)
                articles = articles.object_list
            except Exception as e:
                self.output.error(0, e.message)
                continue

            change_article_author_data(articles, u)


    def change_article_author_data(self, articles, u, esd):
        '''
        Changes to all author preferred name on articles_list for a user.
        Most of the data is from the associated :class:`~openemory.publication.models.Publication` object.
        '''
        

        for a in articles:
            self.output(2, "Getting info for Article %s(%s)" % (a.get('title', '<NO TITLE>').encode('utf-8'), a['pid']))
            obj = self.repo.get_object(pid=a['pid'], type=Publication)
            mods = obj.descMetadata.content
            a = AuthorName(id=u.username.lower(), affiliation='Emory University', given_name=u.first_name, family_name=u.last_name)
            authors = mods.authors
            for author in authors:
                if author.id == u.username.lower():
                    author.given_name = esd.ad_name.split(' ', 1)[0]
                    author.family_name = esd.ad_name.split(' ', 1)[1]

            
            obj.save() # reindexes and saves to fedora

        
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
