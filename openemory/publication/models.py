import logging

from django.contrib.auth.models import User
from eulfedora.models import DigitalObject, FileDatastream, XmlDatastream
from eulfedora.util import RequestFailed
from eulfedora.indexdata.util import pdf_to_text
from eullocal.django.emory_ldap.backends import EmoryLDAPBackend
from eulxml import xmlmap
from eulxml.xmlmap import mods
from pyPdf import PdfFileReader
from rdflib.graph import Graph as RdfGraph
from rdflib import URIRef, RDF, RDFS, Literal

from openemory.rdfns import DC, BIBO, FRBR, ns_prefixes
from openemory.util import pmc_access_url

logger = logging.getLogger(__name__)

class JournalMods(mods.RelatedItem):
    publisher = xmlmap.StringField('mods:originInfo/mods:publisher', required=True)
    volume = xmlmap.NodeField('mods:part/mods:detail[@type="volume"]',
                              mods.PartDetail)
    number = xmlmap.NodeField('mods:part/mods:detail[@type="number"]',
                              mods.PartDetail)
    pages = xmlmap.NodeField('mods:part/mods:extent[@unit="pages"]', mods.PartExtent,
                             required=False)

class FundingGroup(mods.Name):
    name = xmlmap.StringField('mods:namePart')
    
    def __init__(self, *args, **kwargs):        
        super(FundingGroup, self).__init__(*args, **kwargs)
        # make sure the role and type are set correctly when creating
        # a new instance
        if not len(self.roles):
            self.roles.append(mods.Role(type='text', text='funder'))
        self.type = 'corporate'
        
    def is_empty(self):
        '''Returns False unless a namePart value is set; type and role
        are ignored.'''
        return not bool(self.name_parts and self.name_parts[0].text)

class AuthorName(mods.Name):
    family_name = xmlmap.StringField('mods:namePart[@type="family"]')
    given_name = xmlmap.StringField('mods:namePart[@type="given"]')
    def __init__(self, *args, **kwargs):        
        super(AuthorName, self).__init__(*args, **kwargs)
        # make sure the role and type are set correctly when creating
        # a new instance
        if not len(self.roles):
            self.roles.append(mods.Role(type='text', text='author'))
        self.type = 'personal'
        
    def is_empty(self):
        '''Returns False unless a namePart value is set; type and role
        are ignored.'''
        return not bool(self.name_parts and self.name_parts[0].text)


class AuthorNote(mods.TypedNote):
    def __init__(self, *args, **kwargs):
        super(AuthorNote, self).__init__(*args, **kwargs)
        self.type = 'author notes'

class Keyword(mods.Subject):
    def __init__(self, *args, **kwargs):
        super(Keyword, self).__init__(*args, **kwargs)
        self.authority = 'keywords'
    

class ArticleMods(mods.MODSv34):
    authors = xmlmap.NodeListField('mods:name[@type="personal" and mods:role/mods:roleTerm="author"]', AuthorName)
    funders = xmlmap.NodeListField('mods:name[@type="corporate" and mods:role/mods:roleTerm="funder"]',
                               FundingGroup, verbose_name='Funding Group or Granting Agency')
    'external funding group or granting agency supporting research for the article'
    journal = xmlmap.NodeField('mods:relatedItem[@type="host"]',
                               JournalMods)
    'information about the journal where the article was published'
    author_notes = xmlmap.NodeListField('mods:note[@type="author notes"]',
                                        AuthorNote)
    keywords = xmlmap.NodeListField('mods:subject[@authority="keywords"]',
                                   Keyword)
    genre = xmlmap.StringField('mods:genre[@authority="marcgt"]')
    version = xmlmap.StringField('mods:genre[@authority="local"]',
                                 choices=['preprint', 'post-print',
                                          'final publisher PDF'])
    'version of the article being submitted (e.g., preprint, post-print, etc)'


class NlmAuthor(xmlmap.XmlObject):
    '''Minimal wrapper for author in NLM XML'''
    surname = xmlmap.StringField('name/surname')
    '''author surname'''
    given_names = xmlmap.StringField('name/given-names')
    '''author given name(s)'''
    affiliation = xmlmap.StringField('aff')
    '''author institutional affiliation, or None if missing'''
    email = xmlmap.StringField('email')
    '''author email, or None if missing'''


class NlmArticle(xmlmap.XmlObject):
    '''Minimal wrapper for NLM XML article'''
    ROOT_NAME = 'article'

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
        'contrib[@contrib-type="author"]', NlmAuthor)
    '''list of authors contributing to the article (list of
    :class:`NlmAuthor`)'''
    corresponding_author_emails = xmlmap.StringListField('front/article-meta/' +
        'author-notes/corresp/email')
    '''list of email addresses listed in article metadata for correspondence'''
    abstract = xmlmap.NodeField('front/article-meta/abstract', xmlmap.XmlObject)
    '''preliminary mapping to article abstract'''
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


class Article(DigitalObject):
    '''Subclass of :class:`~eulfedora.models.DigitalObject` to
    represent Scholarly Articles.
    
    Following `Hydra content model`_ conventions where appropriate;
    similar to the generic simple Hydra content model
    `genericContent`_.

    .. _Hydra content model: https://wiki.duraspace.org/display/hydra/Hydra+objects%2C+content+models+%28cModels%29+and+disseminators
    .. _genericContent: https://wiki.duraspace.org/display/hydra/Hydra+objects%2C+content+models+%28cModels%29+and+disseminators#Hydraobjects%2Ccontentmodels%28cModels%29anddisseminators-genericContent
    '''
    ARTICLE_CONTENT_MODEL = 'info:fedora/emory-control:PublishedArticle-1.0'
    CONTENT_MODELS = [ ARTICLE_CONTENT_MODEL ]
    
    pdf = FileDatastream('content', 'PDF content', defaults={
        'mimetype': 'application/pdf',
        'versionable': True
        })
    '''PDF content of a scholarly article, stored and accessed as a
    :class:`~eulfedora.models.FileDatastream`; datastream is
    configured to be versioned and managed; default mimetype is
    ``application/pdf``.'''

    descMetadata = XmlDatastream('descMetadata', 'Descriptive Metadata (MODS)',
        ArticleMods, defaults={
            'versionable': True,
        })
    '''Descriptive Metadata datastream, as :class:`ArticleMods`'''

    contentMetadata = XmlDatastream('contentMetadata', 'content metadata', NlmArticle, defaults={
        'versionable': True
        })
    '''Optional datastream for additional content metadata for a
    scholarly article that is not the primary descriptive metadata as an
    :class:`NlmArticle`.'''

    @property
    def number_of_pages(self):
        'The number of pages in the PDF associated with this object'
        try:
            # if this article doesn't have a content datastream, skip it
            if not self.pdf.exists:
    		return None

            pdfreader = PdfFileReader(self.pdf.content)
            return pdfreader.getNumPages()
        except RequestFailed as rf:
            logger.error('Failed to determine number of pages for %s : %s' \
                         % (self.pid, rf))

    def as_rdf(self, node=None):
        '''Information about this Article in RDF format.  Currently,
        makes use of `Bibliographic Ontology`_ and FRBR.
        
        .. _Bibliographic Ontology: http://bibliontology.com/

        :returns: instance of :class:`rdflib.graph.Graph`
        '''
        if node is None:
            node = self.uriref

        rdf = RdfGraph()
        for prefix, ns in ns_prefixes.iteritems():
            rdf.bind(prefix, ns)

        # some redundancy here, for now
        rdf.add((node, RDF.type, BIBO.AcademicArticle))
        rdf.add((node, RDF.type, FRBR.ScholarlyWork))
        if self.number_of_pages:
            rdf.add((node, BIBO.numPages, Literal(self.number_of_pages)))
        
        pmc_url = None
        pmcid = self.pmcid
        if pmcid:
            pmc_url = pmc_access_url(pmcid)
            rdf.add((node, RDFS.seeAlso, URIRef(pmc_url)))

        for el in self.dc.content.elements:
            if el.name == 'identifier' and unicode(el) == pmc_url:
                continue # PMC url is a RDFS:seeAlso, above. skip it here
            rdf.add((node, DC[el.name], Literal(el)))
        return rdf

    def index_data(self):
        '''Extend the default
        :meth:`eulfedora.models.DigitalObject.index_data` method to
        include fields needed for search and display of Article
        objects.'''
        data = super(Article, self).index_data()

        # add full document text from pdf if available
        if self.pdf.exists:
            data['fulltext'] = pdf_to_text(self.pdf.content)

        # index descriptive metadata if available
        if self.descMetadata.exists:
            mods = self.descMetadata.content
            if mods.title:	# replace title set from dc:title
                data['title'] = mods.title
            if mods.funders:
                data['funder'] = [f.name for f in mods.funders]
            if mods.journal:
                if mods.journal.title:
                    data['journal_title'] = mods.journal.title
                if mods.journal.publisher:
                    data['journal_publisher'] = mods.journal.publisher
            if mods.abstract:
                data['abstract'] = mods.abstract.text
            if mods.keywords:
                data['keyword'] = [kw.topic for kw in mods.keywords]
            if mods.author_notes:
                data['author_notes'] = [a.text for a in mods.author_notes]
            if mods.authors:
                mods_authors = ['%s, %s' % (a.family_name, a.given_name)
                                for a in mods.authors]
                # check for dc authors and add to them if set
                if 'creator' in data:
                    data['creator'].extend(mods_authors)
                else:
                    data['creator'] = mods_authors

                data['author_affiliation'] = [a.affiliation
                                              for a in mods.authors
                                              if a.affiliation]

        # get contentMetadata (NLM XML) bits
        if self.contentMetadata.exists:
            nxml = self.contentMetadata.content
            if 'fulltext' not in data and nxml.body:
                data['fulltext'] = unicode(nxml.body)
            if nxml.abstract and \
                   'abstract' not in data:	# let MODS abstract take precedence
                data['abstract'] = unicode(nxml.abstract)


        # index the pubmed central id, if we have one
        pmcid = self.pmcid
        if pmcid:
            data['pmcid'] = pmcid
            if pmcid in data['identifier']:	# don't double-index PMC id
                data['identifier'].remove(pmcid)

        return data

    @property
    def pmcid(self):
        for id in self.dc.content.identifier_list:
            if id.startswith('PMC'):
                return id[3:]
