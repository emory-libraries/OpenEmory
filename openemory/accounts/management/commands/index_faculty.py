# file openemory/accounts/management/commands/index_faculty.py
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

from optparse import make_option
import socket

from django.core.management.base import BaseCommand, CommandError
from eulfedora.server import Repository
from sunburnt import SolrError

from openemory.accounts.models import UserProfile, EsdPerson
from openemory.publication.models import Article, Publication
from openemory.util import solr_interface
from django.conf import settings


class Command(BaseCommand):
    '''Index Faculty ESD information into Solr for searching.
    '''
    help = __doc__

    v_normal = 1  # 1 = normal, 0 = minimal, 2 = all
    v_all = 2

    def handle(self, verbosity=1, *args, **options):

        self.verbosity = int(verbosity)

        if self.verbosity >= self.v_normal:
            print('Indexing ESD data for %d faculty members in Solr' % \
                    (EsdPerson.faculty.all().count(),))

        try:
            solr_url = options.get('index_url', settings.SOLR_SERVER_URL)
            self.solr = solr_interface()
        except socket.error as se:
            raise CommandError('Failed to connect to Solr (%s)' % se)

        try:
            self.update_faculty_index()
        except SolrError as se:
            if 'unknown field' in str(se):
                raise CommandError('Solr unknown field error ' +
                                   '(check that local schema matches running instance)')
            raise CommandError('Solr error (%s)' % se)

    def update_faculty_index(self):

        # get all faculty information currently in solr,
        # to check for changes and faculty no longer in ESD
        self.indexed_faculty_data = dict((f['username'], f)
                                         for f in self.indexed_faculty())
        self.updated_faculty = set()
        self.active_faculty = set()

        # add/update faculty indexes for all ESD faculty persons
        self.index_faculty()
        # remove any previously indexed persons not in current run
        self.remove_deactivated_faculty()
        # update articles for any updated or removed authors
        self.cascade_updated_articles()
        # commit all changes in Solr so they will be immediately available
        self.solr.commit()

    def index_faculty(self):
        '''Add or update solr index for every EsdPerson record in the
        database.  Keeps track of updated and active faculty to allow
        updating related articles and removing deactivated faculty.
        '''
        for p in EsdPerson.faculty.all():

            if self.verbosity >= self.v_all:
                print('Indexing faculty', p.username)
            old_index_data = self.indexed_faculty_data.get(p.username, {})
            index_data = p.index_data()
            if not self.compare_index_data(index_data, old_index_data):
                if self.verbosity >= self.v_all:
                    print('Faculty', p.username, 'has changed.')
                self.updated_faculty.add(p.username)

            self.active_faculty.add(p.username)
            self.solr.add(p.index_data())

    def compare_index_data(self, index_data, old_index_data):
        '''Articles are indexed on author division/department/affiliation.
        Check if any of that author information has changed so that
        associated articles can be updated if necessary.'''
        COMPARE_FIELDS = ['username', 'division_dept_id',
                          'department_name', 'department_shortname',
                          'affiliations']
        for field in COMPARE_FIELDS:
            new_val = self.get_normalized_field_value(index_data, field)
            old_val = old_index_data.get(field, None)

            if new_val and old_val and new_val != old_val and old_val != (new_val,):
                if self.verbosity >= self.v_all:
                    print('(%s) %r != %r' % (field, new_val, old_val))
                return False
        return True

    def get_normalized_field_value(self, index_data, field):
        if hasattr(index_data, field):
            val = getattr(index_data, field)
        else:
            val = index_data.get(field, None)

        if val is None:
            return None
        if hasattr(val, '__iter__'):
            return tuple(str(v) for v in val)
        else:
            return str(val)

    def remove_deactivated_faculty(self):
        '''Check all faculty currently indexed in Solr against updated
        faculty from the database, and remove indexes for any that
        are no longer in the database.
        '''
        for faculty in self.indexed_faculty_data.values():
            if faculty['username'] not in self.active_faculty:
                if self.verbosity >= self.v_all:
                    print('Removing deactivated faculty', faculty['username'])
                self.updated_faculty.add(faculty['username'])
                self.solr.delete(faculty)

    def cascade_updated_articles(self):
        '''Reindex all articles associated with faculty who have been
        updated (either article-indexed person data has changed or
        a previously-indexed faculty member is no longer in ESD).
        '''
        updated_articles = set()
        for username in self.updated_faculty:
            for article in self.articles_by_faculty(username):
                updated_articles.add(article['pid'])

        repo = Repository()
        for pid in updated_articles:
            if self.verbosity >= self.v_all:
                print('Indexing article', pid)
            article = repo.get_object(pid, type=Publication)
            self.solr.add(article.index_data())

    def indexed_faculty(self):
        # generator: return solr data for all currently indexed EsdPerson
        if self.verbosity >= self.v_all:
            print('Fetching indexed faculty')
        q = self.solr.query(record_type=EsdPerson.record_type)
        for faculty in self.all_solr_results(q):
            yield faculty

    def articles_by_faculty(self, username):
        # generator: return solr data for all articles associated with a user
        if self.verbosity >= self.v_all:
            print('Fetching articles by', username)
        try:
            profile = UserProfile.objects.get(user__username=username)
        except UserProfile.DoesNotExist:
            return

        q = profile.recent_articles_query()
        for article in self.all_solr_results(q):
            yield article

    def all_solr_results(self, q):
        PAGE_SIZE = 100
        page = 0
        while True:
            response = q.paginate(start=page * PAGE_SIZE, rows=PAGE_SIZE) \
                .execute()

            for item in response:
                yield item

            # return when there are no more results left
            if not response.result.numFound > PAGE_SIZE * (page + 1):
                return

            page += 1
