# file openemory/publication/symp.py
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

from eulxml import xmlmap


class SympAtom(xmlmap.XmlObject):
    '''Minimal wrapper for SympAtom XML datastream'''
    atom_ns = 'http://www.w3.org/2005/Atom'
    pubs_ns = 'http://www.symplectic.co.uk/publications/atom-api'

    ROOT_NS = atom_ns
    ROOT_NAMESPACES = {'atom': atom_ns, 'pubs': pubs_ns}
    ROOT_NAME = 'feed'


    # docid = xmlmap.IntegerField('front/article-meta/' +
    #         'article-id[@pub-id-type="pmc"]')
    # '''PMC document id from :class:`ESearchResponse`; *not* PMID'''
    # pmid = xmlmap.IntegerField('front/article-meta/' +
    #         'article-id[@pub-id-type="pmid"]')
    # '''PubMed id of the article'''
    # doi = xmlmap.StringField('front/article-meta/' +
    #         'article-id[@pub-id-type="doi"]')
    # '''Digital Object Identifier (DOI) for the article'''
    # journal_title = xmlmap.StringField('front/journal-meta/journal-title|front/journal-meta/journal-title-group/journal-title')
    # '''title of the journal that published the article'''
    # article_title = xmlmap.StringField('front/article-meta/title-group/' +
    #         'article-title')
    # '''title of the article, not including subtitle'''
    # article_subtitle = xmlmap.StringField('front/article-meta/title-group/' +
    #         'subtitle')
    # '''subtitle of the article'''
    # authors = xmlmap.NodeListField('front/article-meta/contrib-group/' +
    #     'contrib[@contrib-type="author"]', NlmAuthor)
    # '''list of authors contributing to the article (list of
    # :class:`NlmAuthor`)'''
    # corresponding_author_emails = xmlmap.StringListField('front/article-meta/' +
    #     'author-notes/corresp/email')
    # '''list of email addresses listed in article metadata for correspondence'''
    # abstract = xmlmap.NodeField('front/article-meta/abstract', NlmAbstract)
    # '''article abstract'''
    # body = xmlmap.NodeField('body', xmlmap.XmlObject)
    # '''preliminary mapping to article body (currently used to
    # determine when full-text of the article is available)'''
    # sponsors = xmlmap.StringListField('front/article-meta/contract-sponsor')
    # '''Sponsor or funding group'''

