'''Tools for querying NCBI Entrez E-utilities, notably including PubMed.'''

from datetime import datetime, timedelta
import logging
from time import sleep
from urllib import urlencode
from eulxml import xmlmap
from django.contrib.auth.models import User
from eullocal.django.emory_ldap.backends import EmoryLDAPBackend

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
                # don't calculate anything larger than seconds: this assumes
                # that EUTILS_QUERY_DELAY_SECONDS < 1day
                delay_seconds = delay.seconds + delay.microseconds / 1000000.0
                logger.debug('EntrezClient sleeping for ' + str(delay_seconds))
                sleep(delay_seconds)
        self.last_query_time = now


class ArticleQuerySet(object):
    def __init__(self, entrez, results, start=None, stop=None, **kwargs):
        self.entrez = entrez
        self.results = results
        self.query_opts = kwargs
        self._chunk = None

        if start is None:
            start = 0
        elif start < 0:
            start = 0
        elif start > self.results.count:
            start = self.results.count

        if stop is None:
            stop = self.results.count
        elif stop < 0:
            stop = 0
        elif stop > self.results.count:
            stop = self.results.count

        if stop < start:
            stop = start

        self.start, self.stop = start, stop

    def __len__(self):
        return self.stop - self.start

    def __getitem__(self, key):
        if isinstance(key, slice):
            if key.step is not None:
                raise TypeError('slicing does not support step')

            if key.start is None:
                start = self.start
            elif key.start < 0:
                start = self.stop + key.start
            else:
                start = self.start + key.start

            if start < self.start:
                start = self.start
            elif start > self.stop:
                start = self.stop

            if key.stop is None:
                stop = self.stop
            elif key.stop < 0:
                stop = self.stop + key.stop
            else:
                stop = self.start + key.stop

            if stop < self.start:
                stop = self.start
            elif stop > self.stop:
                stop = self.stop

            return ArticleQuerySet(self.entrez, self.results,
                    start, stop, **self.query_opts)

        elif isinstance(key, (int, long)):
            if key < 0:
                key = len(self) + key
            if key < 0 or key >= len(self):
                raise IndexError('index out of range')

            if self._chunk is None:
                self._chunk = self._execute()
            return self._chunk.articles[key]

        else:
            raise TypeError('index must be a number or a slice')

    def _execute(self):
        query_opts = self.query_opts.copy()
        query_opts['retstart'] = self.start
        query_opts['retmax'] = len(self)
        return self.entrez.efetch(**query_opts)

    def __iter__(self):
        if self._chunk is None:
            self._chunk = self._execute()
        return iter(self._chunk.articles)


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
    article_subtitle = xmlmap.StringField('front/article-meta/title-group/' +
            'subtitle')
    '''subtitle of the article'''
    authors = xmlmap.NodeListField('front/article-meta/contrib-group/' + 
        'contrib[@contrib-type="author"]', EFetchAuthor)
    '''list of authors contributing to the article (list of
    :class:`EFetchAuthor`)'''
    corresponding_author_emails = xmlmap.StringListField('front/article-meta/' +
        'author-notes/corresp/email')
    '''list of email addresses listed in article metadata for correspondence'''
    body = xmlmap.NodeField('body', xmlmap.XmlObject)
    '''preliminary mapping to article body (currently used to
    determine when full-text of the article is available)'''

    @property
    def fulltext_available(self):
        '''boolean; indicates whether or not the full text of the
        article is included in the fetched article.'''
        return self.body != None

    _identified_authors = None
    def identifiable_authors(self, refresh=False):
        '''Identify any Emory authors for the article and, if
        possible, return a list of corresponding
        :class:`~django.contrib.auth.models.User` objects.

        .. Note::
        
          The current implementation is preliminary and has the
          following **known limitations**:
          
            * Ignores authors that are associated with Emory
              but do not have an Emory email address included in the
              article metadata
            * User look-up uses LDAP, which only finds authors who are
              currently associated with Emory

        By default, caches the identified authors on the first
        look-up, in order to avoid unecessarily repeating LDAP
        queries.  
        '''

        if self._identified_authors is None or refresh:
            # find all author emails, either in author information or corresponding author
            emails = set(auth.email for auth in self.authors if auth.email)
            emails.update(self.corresponding_author_emails)
            # filter to just include the emory email addresses
            # TODO: other acceptable variant emory emails ? emoryhealthcare.org ? 
            emory_emails = [e for e in emails if 'emory.edu' in e ]

            # generate a list of User objects based on the list of emory email addresses
            self._identified_authors = []
            for em in emory_emails:
                # if the user is already in the local database, use that
                db_user = User.objects.filter(email=em)
                if db_user.count() == 1:
                    self._identified_authors.append(db_user.get())

                # otherwise, try to look them up in ldap 
                else:
                    ldap = EmoryLDAPBackend()
                    # log ldap requests; using repr so it is evident when ldap is a Mock
                    logger.debug('Looking up user in LDAP by email \'%s\' (using %r)' \
                                 % (em, ldap))
                    user_dn, user = ldap.find_user_by_email(em)
                    if user:
                        self._identified_authors.append(user)

        return self._identified_authors


class EFetchResponse(xmlmap.XmlObject):
    '''Minimal wrapper for EFetch XML returns'''
    articles = xmlmap.NodeListField('article', EFetchArticle)
    '''list of requested article data as a list of
    :class:`EFetchArticle` objects'''
