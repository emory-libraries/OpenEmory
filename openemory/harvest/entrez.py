'''Tools for querying NCBI Entrez E-utilities, notably including PubMed.'''

from urllib import urlencode
from eulxml import xmlmap

# Developers MUST read E-Utilities guidelines and requirements at:
#   http://www.ncbi.nlm.nih.gov/books/NBK25497/
# Entrez E-utilities docs at:
#   http://www.ncbi.nlm.nih.gov/books/NBK25499/

class EntrezClient(object):
    '''Generic client for making web requests to NCBI Entrez E-utilities in
    accordance with their `guidlines and requirements
    <http://www.ncbi.nlm.nih.gov/books/NBK25497/>`_.
    '''

    QUERY_ROOT = 'http://eutils.ncbi.nlm.nih.gov/entrez/eutils/'
    'URL root of all eutils queries'
    ESEARCH = QUERY_ROOT + 'esearch.fcgi?'
    'URL path of esearch queries'
    ESUMMARY = QUERY_ROOT + 'esummary.fcgi?'
    'URL path of esummary queries'
    EUTILS_TOOL = 'emory-libs-openemory'
    '``tool`` query argument added to all eutils queries'
    EUTILS_EMAIL = 'LIBSYSDEV-L@listserv.cc.emory.edu'
    '``email`` query argument added to all eutils queries'

    def esearch(self, **kwargs):
        '''Query ESearch, forwarding all arguments as URL query arguments.
        Adds ``tool`` and ``email`` query arguments if they are not
        included.

        :returns: :class:`ESearchResponse`
        '''
        return self._query(self.ESEARCH, kwargs, ESearchResponse)

    def _query(self, base_url, qargs, response_xmlclass):
        '''Utility method: Add required query arguments, return response as
        a caller-specified :class:`~eulxml.xmlmap.XmlObject`.
        '''
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
    '''Minimal wrapper for ESearch XML returns'''

    count = xmlmap.IntegerField('Count')
    '''total articles matching the query'''
    query_key = xmlmap.IntegerField('QueryKey')
    '''server-assigned id for this query in history'''
    webenv = xmlmap.StringField('WebEnv')
    '''server-assigned web environment for history management'''
    docid = xmlmap.IntegerListField('IdList/Id')
    '''first page of document UIDs (*not* PMIDs) matching the query'''


class EFetchAuthor(xmlmap.XmlObject):
    '''Minimal wrapper for author in EFetch XML returns'''
    surname = xmlmap.StringField('name/surname')
    given_names = xmlmap.StringField('name/given-names')
    affiliation = xmlmap.StringField('aff')
    email = xmlmap.StringField('email')


class EFetchArticle(xmlmap.XmlObject):
    '''Minimal wrapper for article in EFetch XML returns'''
    journal_title = xmlmap.StringField('front/journal-meta/journal-title')
    article_title = xmlmap.StringField('front/article-meta/title-group/' +
            'article-title')
    authors = xmlmap.NodeListField('front/article-meta/contrib-group/' + 
        'contrib[@contrib-type="author"]', EFetchAuthor)
    corresponding_author_email = xmlmap.StringField('front/article-meta/' +
        'author-notes/corresp/email')


class EFetchResponse(xmlmap.XmlObject):
    '''Minimal wrapper for EFetch XML returns'''
    articles = xmlmap.NodeListField('article', EFetchArticle)
    '''list of requested article data as a list of
    :class:`EFetchArticle` objects'''
