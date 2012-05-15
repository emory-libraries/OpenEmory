from optparse import make_option
import socket

from django.core.management.base import BaseCommand, CommandError
from sunburnt import SolrError

from openemory.accounts.models import EsdPerson
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

        self.verbosity = verbosity

        if self.verbosity >= self.v_normal:
            print 'Indexing ESD data for %d faculty members in Solr' % \
                    (EsdPerson.faculty.all().count(),)

        try:
            solr_url = options.get('index_url', None)
            solr = solr_interface(solr_url)
        except socket.error as se:
            raise CommandError('Failed to connect to Solr (%s)' % se)

        try:
            self.update_faculty_index(solr)
        except SolrError as se:
            if 'unknown field' in str(se):
                raise CommandError('Solr unknown field error ' +
                                   '(check that local schema matches running instance)')
            raise CommandError('Solr error (%s)' % se)

    def update_faculty_index(self, solr):
        active_faculty = set()
        self.index_faculty(solr, active_faculty)
        self.remove_deactivated_faculty(solr, active_faculty)
        solr.commit()

    def index_faculty(self, solr, active_faculty):
        for p in EsdPerson.faculty.all():
            if self.verbosity >= self.v_all:
                print 'Indexing', p.username
            active_faculty.add(p.username)
            solr.add(p.index_data())

    def remove_deactivated_faculty(self, solr, active_faculty):
        PAGE_SIZE = 100
        page = 0
        for faculty in self.indexed_faculty(solr):
            if faculty['username'] not in active_faculty:
                if self.verbosity >= self.v_all:
                    print 'Removing deactivated faculty', faculty['username']
                solr.delete(faculty)

    def indexed_faculty(self, solr):
        PAGE_SIZE = 100
        page = 0
        while True:
            if self.verbosity >= self.v_all:
                print 'Fetching faculty page %d from index' % (page,)
            response = solr.query(record_type=EsdPerson.record_type) \
                           .paginate(start=page * PAGE_SIZE, rows=PAGE_SIZE) \
                           .execute()
            if not list(response):
                # no more results.
                return
            for faculty in response:
                yield faculty

            page += 1
