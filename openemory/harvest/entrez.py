'''tools for querying NCBI Entrez E-utilities, notably including PubMed'''

from urllib import urlencode
from eulxml import xmlmap

# Developers MUST read E-Utilities guidelines and requirements at:
#   http://www.ncbi.nlm.nih.gov/books/NBK25497/
# Entrez E-utilities docs at:
#   http://www.ncbi.nlm.nih.gov/books/NBK25499/

class EntrezClient(object):
    QUERY_ROOT = 'http://eutils.ncbi.nlm.nih.gov/entrez/eutils/'
    ESEARCH = QUERY_ROOT + 'esearch.fcgi?'
    EUTILS_TOOL = 'emory-libs-openemory'
    EUTILS_EMAIL = 'LIBSYSDEV-L@listserv.cc.emory.edu'

    def esearch(self, **kwargs):
        return self._query(self.ESEARCH, kwargs, ESearchResponse)

    def _query(self, base_url, qargs, response_xmlclass):
        qargs = qargs.copy()
        if 'tool' not in qargs:
            qargs['tool'] = self.EUTILS_TOOL
        if 'email' not in qargs:
            qargs['email'] = self.EUTILS_EMAIL
        # TODO: When we start making more than one query we need to sleep to
        # avoid making more than 3 requests per second per E-Utilities
        # policies.
        qurl = base_url + urlencode(qargs)
        return xmlmap.load_xmlobject_from_file(qurl,
                xmlclass=response_xmlclass)

class ESearchResponse(xmlmap.XmlObject):
    count = xmlmap.IntegerField('Count')
    pmid = xmlmap.IntegerListField('IdList/Id')
