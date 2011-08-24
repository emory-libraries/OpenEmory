'''
RDF Namespaces initialized as instances of :class:`rdflib.Namespace`,
along with namespace prefixes, for use accessing and generating RDF content
throughout the application.

'''
from rdflib import Namespace, URIRef
from eulxml.xmlmap.dc import DublinCore

DC = Namespace(URIRef(DublinCore.ROOT_NAMESPACES['dc']))
'Dublin Core'

BIBO = Namespace(URIRef('http://purl.org/ontology/bibo/'))
'Bibliographic Ontology'

FOAF = Namespace(URIRef('http://xmlns.com/foaf/0.1/'))
'Friend-of-a-Friend'

FRBR = Namespace(URIRef('http://purl.org/vocab/frbr/core#'))
'Functional Requirements for Bibliographic Records (FRBR core)'

ns_prefixes = {
    'dc': DC,
    'bibo': BIBO,
    'foaf': FOAF,
    'frbr': FRBR,
}
'''
Prefixes for RDF Namespaces defined here in :mod:`openemory.rdfns`,
for consistency in serializing RDF content throughout the application.
To use, bind each prefixes and corresponding namespace to your graph::


   rdf = rdflib.graph.Graph()
   for prefix, ns in ns_prefixes.iteritems():
      rdf.bind(prefix, ns)
        
'''
