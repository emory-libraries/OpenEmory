# file openemory/rdfns.py
# 
#   Copyright 2010 Emory University General Library
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

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
   for prefix, ns in ns_prefixes.items():
      rdf.bind(prefix, ns)
        
'''
