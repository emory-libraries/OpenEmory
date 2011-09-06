'''Tools for querying NCBI Entrez E-utilities, notably including PubMed.'''

from datetime import datetime, timedelta
import logging
from time import sleep
from urllib import urlencode
from eulxml import xmlmap

# Developers MUST read E-Utilities guidelines and requirements at:
#   http://www.ncbi.nlm.nih.gov/books/NBK25497/
# Entrez E-utilities docs at:
#   http://www.ncbi.nlm.nih.gov/books/NBK25499/

logger = logging.getLogger(__name__)

class EntrezClient(object):
    '''Generic client for making web requests to NCBI Entrez E-utilities in
    accordance with their `guidlines and requirements
    <http://www.ncbi.nlm.nih.gov/books/NBK25497/>`_.
    '''

    QUERY_ROOT = 'http://eutils.ncbi.nlm.nih.gov/entrez/eutils/'
    'URL root of all eutils queries'
    ESEARCH = QUERY_ROOT + 'esearch.fcgi?'
    'URL path of esearch queries'
    EFETCH = QUERY_ROOT + 'efetch.fcgi?'
    'URL path of efetch queries'
    ESUMMARY = QUERY_ROOT + 'esummary.fcgi?'
    'URL path of esummary queries'
    EUTILS_TOOL = 'emory-libs-openemory'
    '``tool`` query argument added to all eutils queries'
    EUTILS_EMAIL = 'LIBSYSDEV-L@listserv.cc.emory.edu'
    '``email`` query argument added to all eutils queries'
    EUTILS_QUERY_DELAY_SECONDS = 0.34
    'minimum seconds to pause between consecutive eutils requests'

    def __init__(self):
        self.last_query_time = None

    def esearch(self, **kwargs):
        '''Query ESearch, forwarding all arguments as URL query arguments.
        Adds ``tool`` and ``email`` query arguments if they are not
        included.

        :returns: :class:`ESearchResponse`
        '''
        return self._query(self.ESEARCH, kwargs, ESearchResponse)

    def efetch(self, **kwargs):
        '''Query EFetch, forwarding all arguments as URL query arguments.
        Adds ``tool``, ``email``, and ``retmode`` query arguments if they
        are not included.

        :returns: :class:`EFetchResponse`
        '''
        if 'retmode' not in kwargs:
            kwargs = kwargs.copy()
            kwargs['retmode'] = 'xml'
        return self._query(self.EFETCH, kwargs, EFetchResponse)

    def _query(self, base_url, qargs, response_xmlclass):
        '''Utility method: Adds required query arguments, returns response
        as a caller-specified :class:`~eulxml.xmlmap.XmlObject`. Delays if
        necessary to enforce EUtils query speed policy.
        '''
        self._enforce_query_timing()
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

    def _enforce_query_timing(self):
        '''Enforce EUtils query speed policy by sleeping to keep queries
        separated by at least :data:`EUTILS_QUERY_DELAY_SECONDS`.
        '''
        now = datetime.now()
        if self.last_query_time is not None:
            next_query_allowed = self.last_query_time + timedelta(seconds=self.EUTILS_QUERY_DELAY_SECONDS)
            logger.debug('EntrezClient timing next=%s; now=%s' % \
                    (str(next_query_allowed), str(now)))
            if now < next_query_allowed:
                delay = next_query_allowed - now
                delay_seconds = delay.total_seconds()
                logger.debug('EntrezClient sleeping for ' + str(delay_seconds))
                sleep(delay_seconds)
        self.last_query_time = now


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
    '''author surname'''
    given_names = xmlmap.StringField('name/given-names')
    '''author given name(s)'''
    affiliation = xmlmap.StringField('aff')
    '''author institutional affiliation, or None if missing'''
    email = xmlmap.StringField('email')
    '''author email, or None if missing'''


class EFetchArticle(xmlmap.XmlObject):
    '''Minimal wrapper for article in EFetch XML returns'''
    docid = xmlmap.IntegerField('front/article-meta/' +
            'article-id[@pub-id-type="pmc"]')
    '''PMC document id from :class:`ESearchResponse`; *not* PMID'''
    pmid = xmlmap.IntegerField('front/article-meta/' +
            'article-id[@pub-id-type="pmid"]')
    '''PubMed id of the article'''
    journal_title = xmlmap.StringField('front/journal-meta/journal-title')
    '''title of the journal that published the article'''
    article_title = xmlmap.StringField('front/article-meta/title-group/' +
            'article-title')
    '''title of the article, not including subtitle'''
    authors = xmlmap.NodeListField('front/article-meta/contrib-group/' + 
        'contrib[@contrib-type="author"]', EFetchAuthor)
    '''list of authors contributing to the article (list of
    :class:`EFetchAuthor`)'''
    corresponding_author_email = xmlmap.StringField('front/article-meta/' +
        'author-notes/corresp/email')
    '''email address listed in article metadata for correspondence, or None
    if missing'''


class EFetchResponse(xmlmap.XmlObject):
    '''Minimal wrapper for EFetch XML returns'''
    articles = xmlmap.NodeListField('article', EFetchArticle)
    '''list of requested article data as a list of
    :class:`EFetchArticle` objects'''
