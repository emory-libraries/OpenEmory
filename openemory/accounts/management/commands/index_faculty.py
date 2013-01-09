from optparse import make_option
import socket

from django.core.management.base import BaseCommand, CommandError
from eulfedora.server import Repository
from sunburnt import SolrError

from openemory.accounts.models import UserProfile, EsdPerson
from openemory.publication.models import Article
from openemory.util import solr_interface


class Command(BaseCommand):
    '''Index Faculty ESD information into Solr for searching.
    '''
    help = __doc__

    option_list = BaseCommand.option_list + (
        make_option('-i', '--index_url',
                    help='Override the site default solr index URL.'),
    )

    v_normal = 1  # 1 = normal, 0 = minimal, 2 = all
    v_all = 2

    def handle(self, verbosity=1, *args, **options):

        self.verbosity = int(verbosity)

        if self.verbosity >= self.v_normal:
            print 'Indexing ESD data for %d faculty members in Solr' % \
                    (EsdPerson.faculty.all().count(),)

        try:
            solr_url = options.get('index_url', None)
            self.solr = solr_interface(solr_url)
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
        self.indexed_faculty_data = dict((f['username'], f)
                                         for f in self.indexed_faculty())
        self.updated_faculty = set()
        self.active_faculty = set()

        self.index_faculty()
        self.remove_deactivated_faculty()
        self.cascade_updated_articles()
        self.solr.commit()

    def index_faculty(self):
        for p in EsdPerson.faculty.all():

            if self.verbosity >= self.v_all:
                print 'Indexing faculty', p.username
            old_index_data = self.indexed_faculty_data.get(p.username, {})
            index_data = p.index_data()
            if not self.compare_index_data(index_data, old_index_data):
                if self.verbosity >= self.v_all:
                    print 'Faculty', p.username, 'has changed.'
                self.updated_faculty.add(p.username)

            self.active_faculty.add(p.username)
            self.solr.add(p.index_data())

    def compare_index_data(self, index_data, old_index_data):
        COMPARE_FIELDS = ['username', 'division_dept_id',
                          'department_name', 'department_shortname',
                          'affiliations']
        for field in COMPARE_FIELDS:
            new_val = self.get_normalized_field_value(index_data, field)
            old_val = old_index_data.get(field, None)

            if new_val and old_val and new_val != old_val and old_val != (new_val,):
                if self.verbosity >= self.v_all:
                    print '(%s) %r != %r' % (field, new_val, old_val)
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
        PAGE_SIZE = 100
        page = 0
        for faculty in self.indexed_faculty_data.itervalues():
            if faculty['username'] not in self.active_faculty:
                if self.verbosity >= self.v_all:
                    print 'Removing deactivated faculty', faculty['username']
                self.updated_faculty.add(faculty['username'])
                self.solr.delete(faculty)

    def cascade_updated_articles(self):
        updated_articles = set()
        for username in self.updated_faculty:
            for article in self.articles_by_faculty(username):
                updated_articles.add(article['pid'])

        repo = Repository()
        for pid in updated_articles:
            if self.verbosity >= self.v_all:
                print 'Indexing article', pid
            article = repo.get_object(pid, type=Article)
            self.solr.add(article.index_data())

    def indexed_faculty(self):
        if self.verbosity >= self.v_all:
            print 'Fetching indexed faculty'
        q = self.solr.query(record_type=EsdPerson.record_type)
        for faculty in self.all_solr_results(q):
            yield faculty

    def articles_by_faculty(self, username):
        if self.verbosity >= self.v_all:
            print 'Fetching articles by', username
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
            if self.verbosity >= self.v_all:
                print 'Fetching index page %d' % (page,)
            response = q.paginate(start=page * PAGE_SIZE, rows=PAGE_SIZE) \
            .execute()
            if not list(response):
                # no more results.
                return
            for item in response:
                yield item

            page += 1
