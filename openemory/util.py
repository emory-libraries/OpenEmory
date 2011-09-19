'''
Common utility methods used elsewhere in the site.

'''

import hashlib
import httplib2
from django.conf import settings
import sunburnt

def md5sum(filename):
    '''Calculate and returns an MD5 checksum for the specified file.  Any file
    errors (non-existent file, read error, etc.) are not handled here but should
    be caught where this method is called.

    :param filename: full path to the file for which a checksum should be calculated
    :returns: hex-digest formatted MD5 checksum as a string
    '''
    # copied from keep.common.utils
    md5 = hashlib.md5()
    with open(filename,'rb') as f:
        for chunk in iter(lambda: f.read(128*md5.block_size), ''):
             md5.update(chunk)
    return md5.hexdigest()


def pmc_access_url(pmcid):
    'Direct link to a PubMed Central article based on PubMed Central ID.'
    return 'http://www.ncbi.nlm.nih.gov/pmc/articles/PMC%d/' % (pmcid,)


def solr_interface():
    http_opts = {}
    if hasattr(settings, 'SOLR_CA_CERT_PATH'):
        http_opts['ca_certs'] = settings.SOLR_CA_CERT_PATH
    http = httplib2.Http(**http_opts)
    solr = sunburnt.SolrInterface(settings.SOLR_SERVER_URL,
                                  http_connection=http)
    return solr
