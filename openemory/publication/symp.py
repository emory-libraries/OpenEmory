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

class SympUser(xmlmap.XmlObject):
    '''
    Information about a user in Elements
    '''
    id = xmlmap.StringField('pubs:id')
    '''Elements user id'''
    username = xmlmap.StringField('pubs:username')
    '''netid of user'''
    proprietary_id = xmlmap.StringField('pubs:proprietary-id')
    '''Person id'''
    initials = xmlmap.StringField('pubs:initials')
    '''initials of user'''
    last_name = xmlmap.StringField('pubs:last-name')
    '''last name of user'''
    first_name = xmlmap.StringField('pubs:first-name')
    '''first name of user'''
    email = xmlmap.StringField('pubs:email-address')
    '''email address of user'''

class SympDate(xmlmap.XmlObject):
    '''
    Information about a date in Elements
    '''
    year = xmlmap.StringField('pubs:year')
    '''Four digit year'''
    month = xmlmap.StringField('pubs:month')
    '''Month of year'''
    day = xmlmap.StringField('pubs:day')
    '''Day of month'''

    def date_info(self):
        """
        Array of date values that exist
        :return: Array of year, month , day values
        """
        info= []

        if self.year: info.append(self.year)
        if self.month: info.append(self.month.zfill(2))
        if self.day: info.append(self.day.zfill(2))

        return info
    @property
    def date_str(self):
        """
        Formats date YYYY-MM-DD-DD
        :return: YYYY-MM-DD  or YYYY-MM  or YYYY
        """
        return '-'.join(self.date_info())



class SympPages(xmlmap.XmlObject):
    """
    Contains begin and end page info
    """
    begin_page = xmlmap.StringField("pubs:begin-page")
    '''Start page for item of scholarship'''
    end_page = xmlmap.StringField("pubs:end-page")
    '''End page for item of scholarship'''

class SympSource(xmlmap.XmlObject):
    '''
    A single Source in :class: `SympAtom`
    '''
    source_name = xmlmap.StringField('pubs:data-source/pubs:source-name')
    '''Specifies source of the information'''

    title = xmlmap.StringField("pubs:bibliographic-data/pubs:native/pubs:field[@name='title']/pubs:text")
    '''Title of scholarship item'''
    language = xmlmap.StringField("pubs:bibliographic-data/pubs:native/pubs:field[@name='language']/pubs:text")
    '''Language of scholarship item'''
    abstract = xmlmap.StringField("pubs:bibliographic-data/pubs:native/pubs:field[@name='abstract']/pubs:text")
    '''Abstract of scholarship item'''
    volume = xmlmap.StringField("pubs:bibliographic-data/pubs:native/pubs:field[@name='volume']/pubs:text")
    '''Volume item of scholarship apeared in'''
    issue = xmlmap.StringField("pubs:bibliographic-data/pubs:native/pubs:field[@name='issue']/pubs:text")
    '''Issee item of scholarship apeared in'''
    pubdate = xmlmap.NodeField("pubs:bibliographic-data/pubs:native/pubs:field[@name='publication-date']/pubs:date", SympDate)
    '''Date item of scholarship was published'''
    pages = xmlmap.NodeField("pubs:bibliographic-data/pubs:native/pubs:field[@name='pagination']/pubs:pagination", SympPages)
    '''Start page for item of scholarship'''
    publisher = xmlmap.StringField("pubs:bibliographic-data/pubs:native/pubs:field[@name='publisher']/pubs:text")
    '''Publisher of item of scholarship'''
    journal = xmlmap.StringField("pubs:bibliographic-data/pubs:native/pubs:field[@name='journal']/pubs:text")
    '''Journal item of scholarship apeared in'''
    doi = xmlmap.StringField("pubs:bibliographic-data/pubs:native/pubs:field[@name='doi']/pubs:text")
    '''doi for item of scholarship'''
    keywords = xmlmap.StringListField("pubs:bibliographic-data/pubs:native/pubs:field[@name='keywords']/pubs:keywords/pubs:keyword")
    '''Keywords for item of scholarship'''


class SympAtom(xmlmap.XmlObject):
    '''Minimal wrapper for SympAtom XML datastream'''
    atom_ns = 'http://www.w3.org/2005/Atom'
    pubs_ns = 'http://www.symplectic.co.uk/publications/atom-api'

    ROOT_NS = atom_ns
    ROOT_NAMESPACES = {'atom': atom_ns, 'pubs': pubs_ns}
    ROOT_NAME = 'feed'

    categories = xmlmap.StringListField('atom:category/@label')
    '''Contains lables including what type of object this is'''
    users = xmlmap.NodeListField('pubs:users/pubs:user', SympUser)
    '''list of associated :class: `SympUser` objects'''
    embargo = xmlmap.StringField("pubs:fields/pubs:field[@name='requested-embargo-period']/pubs:text")
    '''Requested Embargo duration'''

    #access props for each field

    @property
    def title(self):
        '''wrapper arond field that chooses that prefered source'''
        if self.wos and self.wos.title:
            return self.wos.title
        elif self.scopus and self.scopus.title:
            return self.scopus.title
        elif self.pubmed and self.pubmed.title:
            return self.pubmed.title
        elif self.crossref and self.crossref.title:
            return self.crossref.title
        elif self.arxiv and self.arxiv.title:
            return self.arxiv.title
        elif self.repec and self.repec.title:
            return self.repec.title
        elif self.dblp and self.dblp.title:
            return self.dblp.title
        else: return ''



    @property
    def language(self):
        '''
        wrapper arond field that chooses that prefered source
         :returns: a tuple containng language code and name
        '''
        marc_languages_xml = 'http://www.loc.gov/standards/codelists/languages.xml'
        langs =  xmlmap.load_xmlobject_from_file(marc_languages_xml)

        ns = {'lang':'info:lc/xmlns/codelist-v1'}

        if self.wos and self.wos.language:
            lang = self.wos.language
        elif self.scopus and self.scopus.language:
            lang = self.scopus.language
        elif self.pubmed and self.pubmed.language:
            lang = self.pubmed.language
        elif self.crossref and self.crossref.language:
            lang = self.crossref.language
        elif self.arxiv and self.arxiv.language:
            lang = self.arxiv.language
        elif self.repec and self.repec.language:
            lang = self.repec.language
        elif self.dblp and self.dblp.language:
            lang = self.dblp.language
        else: lang = ''


        node = langs.node.xpath("//lang:language[lang:name='%s' or lang:code='%s']" % (lang, lang), namespaces=ns)[0]
        return (node.findtext('lang:code', namespaces=ns), node.findtext('lang:name', namespaces=ns))


    @property
    def abstract(self):
        if self.wos and self.wos.abstract:
            return self.wos.abstract
        elif self.scopus and self.scopus.abstract:
            return self.scopus.abstract
        elif self.pubmed and self.pubmed.abstract:
            return self.pubmed.abstract
        elif self.crossref and self.crossref.abstract:
            return self.crossref.abstract
        elif self.arxiv and self.arxiv.abstract:
            return self.arxiv.abstract
        elif self.repec and self.repec.abstract:
            return self.repec.abstract
        elif self.dblp and self.dblp.abstract:
            return self.dblp.abstract
        else: return ''

    @property
    def volume(self):
        '''wrapper arond field that chooses that prefered source'''
        if self.wos and self.wos.volume:
            return self.wos.volume
        elif self.scopus and self.scopus.volume:
            return self.scopus.volume
        elif self.pubmed and self.pubmed.volume:
            return self.pubmed.volume
        elif self.crossref and self.crossref.volume:
            return self.crossref.volume
        elif self.arxiv and self.arxiv.volume:
            return self.arxiv.volume
        elif self.repec and self.repec.volume:
            return self.repec.volume
        elif self.dblp and self.dblp.volume:
            return self.dblp.volume
        else: return ''

    @property
    def issue(self):
        '''wrapper arond field that chooses that prefered source'''
        if self.wos and self.wos.issue:
            return self.wos.issue
        elif self.scopus and self.scopus.issue:
            return self.scopus.issue
        elif self.pubmed and self.pubmed.issue:
            return self.pubmed.issue
        elif self.crossref and self.crossref.issue:
            return self.crossref.issue
        elif self.arxiv and self.arxiv.issue:
            return self.arxiv.issue
        elif self.repec and self.repec.issue:
            return self.repec.issue
        elif self.dblp and self.dblp.issue:
            return self.dblp.issue
        else: return ''


    @property
    def pubdate(self):
        '''
        wrapper arond field that chooses that prefered source
         :returns: :class: `SympDate`
        '''
        if self.wos and self.wos.pubdate:
            return self.wos.pubdate
        elif self.scopus and self.scopus.pubdate:
            return self.scopus.pubdate
        elif self.pubmed and self.pubmed.pubdate:
            return self.pubmed.pubdate
        elif self.crossref and self.crossref.pubdate:
            return self.crossref.pubdate
        elif self.arxiv and self.arxiv.pubdate:
            return self.arxiv.pubdate
        elif self.repec and self.repec.pubdate:
            return self.repec.pubdate
        elif self.dblp and self.dblp.pubdate:
            return self.dblp.pubdate
        else: return ''

    @property
    def pages(self):
        '''
        wrapper arond field that chooses that prefered source
        :returns: :class: `SympPages`
        '''
        if self.wos and self.wos.pages and self.wos.pages.begin_page:
            return self.wos.pages
        elif self.scopus and self.scopus.pages and self.scopus.pages.begin_page:
            return self.scopus.pages
        elif self.pubmed and self.pubmed.pages and self.pubmed.pages.begin_page:
            return self.pubmed.pages
        elif self.crossref and self.crossref.pages and self.crossref.pages.begin_page:
            return self.crossref.pages
        elif self.arxiv and self.arxiv.pages and self.arxiv.pages.begin_page:
            return self.arxiv.pages
        elif self.repec and self.repec.pages and self.repec.pages.begin_page:
            return self.repec.pages
        elif self.dblp and self.dblp.pages and self.dblp.pages.begin_page:
            return self.dblp.pages
        else: return ''


    @property
    def publisher(self):
        '''wrapper arond field that chooses that prefered source'''
        if self.wos and self.wos.publisher:
            return self.wos.publisher
        elif self.scopus and self.scopus.publisher:
            return self.scopus.publisher
        elif self.pubmed and self.pubmed.publisher:
            return self.pubmed.publisher
        elif self.crossref and self.crossref.publisher:
            return self.crossref.publisher
        elif self.arxiv and self.arxiv.publisher:
            return self.arxiv.publisher
        elif self.repec and self.repec.publisher:
            return self.repec.publisher
        elif self.dblp and self.dblp.publisher:
            return self.dblp.publisher
        else: return ''

    @property
    def journal(self):
        '''wrapper arond field that chooses that prefered source'''
        if self.wos and self.wos.journal:
            return self.wos.journal
        elif self.scopus and self.scopus.journal:
            return self.scopus.journal
        elif self.pubmed and self.pubmed.journal:
            return self.pubmed.journal
        elif self.crossref and self.crossref.journal:
            return self.crossref.journal
        elif self.arxiv and self.arxiv.journal:
            return self.arxiv.journal
        elif self.repec and self.repec.journal:
            return self.repec.journal
        elif self.dblp and self.dblp.journal:
            return self.dblp.journal
        else: return ''

    @property
    def doi(self):
        '''wrapper arond field that chooses that prefered source'''
        if self.wos and self.wos.doi:
            return self.wos.doi
        elif self.scopus and self.scopus.doi:
            return self.scopus.doi
        elif self.pubmed and self.pubmed.doi:
            return self.pubmed.doi
        elif self.crossref and self.crossref.doi:
            return self.crossref.doi
        elif self.arxiv and self.arxiv.doi:
            return self.arxiv.doi
        elif self.repec and self.repec.doi:
            return self.repec.doi
        elif self.dblp and self.dblp.doi:
            return self.dblp.doi
        else: return ''

    @property
    def keywords(self):
        '''wrapper arond field that chooses that prefered source'''
        if self.wos and self.wos.keywords:
            return self.wos.keywords
        elif self.scopus and self.scopus.keywords:
            return self.scopus.keywords
        elif self.pubmed and self.pubmed.keywords:
            return self.pubmed.keywords
        elif self.crossref and self.crossref.keywords:
            return self.crossref.keywords
        elif self.arxiv and self.arxiv.keywords:
            return self.arxiv.keywords
        elif self.repec and self.repec.keywords:
            return self.repec.keywords
        elif self.dblp and self.dblp.keywords:
            return self.dblp.keywords
        else: return ''

    # avaliable sources
    wos = xmlmap.NodeField("atom:entry[pubs:data-source/pubs:source-name='web-of-science']", SympSource)
    scopus = xmlmap.NodeField("atom:entry[pubs:data-source/pubs:source-name='scopus']", SympSource)
    pubmed = xmlmap.NodeField("atom:entry[pubs:data-source/pubs:source-name='pubmed']", SympSource)
    # Euro Pubmed
    crossref = xmlmap.NodeField("atom:entry[pubs:data-source/pubs:source-name='crossref']", SympSource)
    arxiv = xmlmap.NodeField("atom:entry[pubs:data-source/pubs:source-name='arxiv']", SympSource)
    # FigShare
    repec = xmlmap.NodeField("atom:entry[pubs:data-source/pubs:source-name='repec']", SympSource)
    # CiNiien
    dblp = xmlmap.NodeField("atom:entry[pubs:data-source/pubs:source-name='dblp']", SympSource)