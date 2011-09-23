from eulfedora.models import DigitalObject, FileDatastream
from eulfedora.util import RequestFailed
import logging
from pyPdf import PdfFileReader
from rdflib.graph import Graph as RdfGraph
from rdflib import Namespace, URIRef, RDF, RDFS, Literal

from openemory.rdfns import DC, BIBO, FRBR, ns_prefixes
from openemory.util import pmc_access_url

logger = logging.getLogger(__name__)

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

    contentMetadata = FileDatastream('contentMetadata', 'content metadata', defaults={
        'mimetype': 'application/xml',
        'versionable': True
        })
    '''Optional datastream for additional content metadata for a
    scholarly article that is not the primary descriptive metadata;
    e.g., for an article harvested from PubMed Central, this
    datastream would contain the NLM XML (either metadata only or
    metadata + full article content).  Stored and accessed as a
    :class:`~eulfedora.models.FileDatastream`; datastream is
    configured to be versioned and managed; default mimetype is
    ``application/xml``, but mimetype and format should be set to
    match the content of the datastream.'''

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
