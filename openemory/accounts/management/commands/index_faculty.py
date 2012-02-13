from django.core.management.base import BaseCommand, CommandError
from openemory.accounts.models import EsdPerson
from openemory.util import solr_interface
import socket
from sunburnt import SolrError


class Command(BaseCommand):
    '''Index Faculty ESD information into Solr for searching.
    '''
    help = __doc__

    v_normal = 1  # 1 = normal, 0 = minimal, 2 = all
    
    def handle(self, verbosity=1, *args, **options):

        if verbosity >= self.v_normal:
            self.stdout.write('Indexing ESD data for %d faculty members in Solr\n' % \
                              EsdPerson.faculty.all().count())
        try:
            solr = solr_interface()
        except socket.error as se:
            raise CommandError('Failed to connect to Solr (%s)' % se)

        try:
            solr.add((p.index_data() for p in EsdPerson.faculty.all()),
                     chunk=100)
        except SolrError as se:
            if 'unknown field' in str(se):
                raise CommandError('Solr unknown field error ' +
                                   '(check that local schema matches running instance)')
            raise CommandError('Solr error (%s)' % se)
