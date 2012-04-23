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
    
    def handle(self, verbosity=1, *args, **options):

        if verbosity >= self.v_normal:
            self.stdout.write('Indexing ESD data for %d faculty members in Solr\n' % \
                              EsdPerson.faculty.all().count())

        try:
            solr_url = options.get('index_url', None)
            solr = solr_interface(solr_url)
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
