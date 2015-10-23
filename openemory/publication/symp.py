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


# stays intact
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


# stays intact
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
        if self.date_info():
            return '-'.join(self.date_info())
        else:
            return ''


# stays intact
class SympPages(xmlmap.XmlObject):
    """
    Contains begin and end page info
    """
    begin_page = xmlmap.StringField("pubs:begin-page")
    '''Start page for item of scholarship'''
    end_page = xmlmap.StringField("pubs:end-page")
    '''End page for item of scholarship'''
    end_page = xmlmap.StringField("pubs:page-count")
    '''End page for item of scholarship'''


# expand for other content types
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

    
    license = xmlmap.StringField("pubs:bibliographic-data/pubs:native/pubs:field[@name='publisher-licence']/pubs:text")
    '''Publisher of item of scholarship'''
    pubstatus = xmlmap.StringField("pubs:bibliographic-data/pubs:native/pubs:field[@name='publication-status']/pubs:text")
    '''Publication Status of item of scholarship'''
    pubnumber = xmlmap.StringField("pubs:bibliographic-data/pubs:native/pubs:field[@name='number']/pubs:text")
    '''Publication Status of item of scholarship'''
    notes = xmlmap.StringField("pubs:bibliographic-data/pubs:native/pubs:field[@name='notes']/pubs:text")
    '''Author notes of item of scholarship'''

    

    ########## additional metadata for all other content types ################

    # conference specific fields
    conference_start = xmlmap.NodeField("pubs:bibliographic-data/pubs:native/pubs:field[@name='start-date']/pubs:date", SympDate)
    '''Conference start date item of scholarship was published'''
    conference_end = xmlmap.NodeField("pubs:bibliographic-data/pubs:native/pubs:field[@name='finish-date']/pubs:date", SympDate)
    '''Conference finish date item of scholarship was published'''
    conference_name = xmlmap.StringField("pubs:bibliographic-data/pubs:native/pubs:field[@name='name-of-conference']/pubs:text")
    '''Conference name of item of scholarship'''
    conference_place = xmlmap.StringField("pubs:bibliographic-data/pubs:native/pubs:field[@name='location']/pubs:text")
    '''Conference location of item of scholarship'''
    acceptance_date = xmlmap.NodeField("pubs:bibliographic-data/pubs:native/pubs:field[@name='acceptance-date']/pubs:date", SympDate)
    '''Conference finish date item of scholarship was published'''
    issue = xmlmap.StringField("pubs:bibliographic-data/pubs:native/pubs:field[@name='issue']/pubs:text")
    '''Issue item of scholarship apeared in'''

    # book and book chapter specific fields
    book_title = xmlmap.StringField("pubs:bibliographic-data/pubs:native/pubs:field[@name='parent-title']/pubs:text")
    '''Book title of item of scholarship'''
    series = xmlmap.StringField("pubs:bibliographic-data/pubs:native/pubs:field[@name='series']/pubs:text")
    '''Series item of scholarship apeared in'''
    edition = xmlmap.StringField("pubs:bibliographic-data/pubs:native/pubs:field[@name='edition']/pubs:text")
    '''Series item of scholarship apeared in'''
    

    ################## Additional fields not found in OpenEmory
    relationship = xmlmap.StringField("pubs:relationships/pubs:relationship/pubs:user-preferences/pubs:data-source")
    medium = xmlmap.StringField("pubs:field[@name='medium']/pubs:text")
    num_chapters = xmlmap.StringField("pubs:field[@name='number-of-pieces']/pubs:text")
    
    pub_place = xmlmap.StringField("pubs:field[@name='place-of-publication']/pubs:text")
    pub_url = xmlmap.StringField("pubs:field[@name='publisher-url']/pubs:text")
    isbn10 = xmlmap.StringField("pubs:field[@name='isbn-10']/pubs:text")

    isbn13 = xmlmap.StringField("pubs:field[@name='isbn-13']/pubs:text")
    author_url = xmlmap.StringField("pubs:field[@name='author-url']/pubs:text")
    author_address = xmlmap.StringField("pubs:field[@name='addresses']/pubs:addresses/pubs:address/pubs:line")
    
        # reports
    confidential = xmlmap.StringField("pubs:field[@name='confidential']/pubs:boolean")
    sponsor = xmlmap.StringField("pubs:field[@name='commissioning-body']/pubs:text")
    
        # conference
    issn = xmlmap.StringField("pubs:field[@name='issn']/pubs:text")
        # book chapter
    chapter_num = xmlmap.StringField("pubs:field[@name='number']/pubs:text")

    ########## end additional metadata for all other content types ################
   


# expand for other content types
class SympAtom(xmlmap.XmlObject):
    '''Minimal wrapper for SympAtom XML datastream'''
    atom_ns = 'http://www.w3.org/2005/Atom'
    pubs_ns = 'http://www.symplectic.co.uk/publications/atom-api'

    ROOT_NS = atom_ns
    ROOT_NAMESPACES = {'atom': atom_ns, 'pubs': pubs_ns}
    ROOT_NAME = 'feed'

    pubs_id = xmlmap.StringField('pubs:id')
    '''This is the coresponding id for the pubs pid and id in Elements'''
    categories = xmlmap.StringListField('atom:category/@label')
    '''Contains lables including what type of object this is'''
    users = xmlmap.NodeListField('pubs:users/pubs:user', SympUser)
    people = xmlmap.NodeListField('pubs:people/pubs:person', SympUser)
    '''list of associated :class: `SympUser` objects'''
    embargo = xmlmap.StringField("pubs:fields/pubs:field[@name='requested-embargo-period']/pubs:text")
    '''Requested Embargo duration'''

    comment = xmlmap.StringField("pubs:fields/pubs:field[@name='fulltext-comment']/pubs:text")
    '''Comment on publication when depositing in OpenEmory through connector'''


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
        elif self.dblp and self.manual.title:
            return self.manual.title
        else: return ''

    @property
    def license(self):
        '''wrapper arond field that chooses that prefered source'''
        if self.wos and self.wos.license:
            return self.wos.license
        elif self.scopus and self.scopus.license:
            return self.scopus.license
        elif self.pubmed and self.pubmed.license:
            return self.pubmed.license
        elif self.crossref and self.crossref.license:
            return self.crossref.license
        elif self.arxiv and self.arxiv.license:
            return self.arxiv.license
        elif self.repec and self.repec.license:
            return self.repec.license
        elif self.dblp and self.dblp.license:
            return self.dblp.license
        elif self.dblp and self.manual.license:
            return self.manual.licence
        else: return ''

    @property
    def pubstatus(self):
        '''wrapper arond field that chooses that prefered source'''
        if self.wos and self.wos.pubstatus:
            return self.wos.pubstatus
        elif self.scopus and self.scopus.pubstatus:
            return self.scopus.pubstatus
        elif self.pubmed and self.pubmed.pubstatus:
            return self.pubmed.pubstatus
        elif self.crossref and self.crossref.pubstatus:
            return self.crossref.pubstatus
        elif self.arxiv and self.arxiv.pubstatus:
            return self.arxiv.pubstatus
        elif self.repec and self.repec.pubstatus:
            return self.repec.pubstatus
        elif self.dblp and self.dblp.pubstatus:
            return self.dblp.pubstatus
        elif self.dblp and self.manual.pubstatus:
            return self.manual.pubstatus
        else: return ''

    @property
    def pubnumber(self):
        '''wrapper arond field that chooses that prefered source'''
        if self.wos and self.wos.pubnumber:
            return self.wos.pubnumber
        elif self.scopus and self.scopus.pubnumber:
            return self.scopus.pubnumber
        elif self.pubmed and self.pubmed.pubnumber:
            return self.pubmed.pubnumber
        elif self.crossref and self.crossref.pubnumber:
            return self.crossref.pubnumber
        elif self.arxiv and self.arxiv.pubnumber:
            return self.arxiv.pubnumber
        elif self.repec and self.repec.pubnumber:
            return self.repec.pubnumber
        elif self.dblp and self.dblp.pubnumber:
            return self.dblp.pubnumber
        elif self.dblp and self.manual.pubnumber:
            return self.manual.pubnumber
        else: return ''

    @property
    def notes(self):
        '''wrapper arond field that chooses that prefered source'''
        if self.wos and self.wos.notes:
            return self.wos.notes
        elif self.scopus and self.scopus.notes:
            return self.scopus.notes
        elif self.pubmed and self.pubmed.notes:
            return self.pubmed.notes
        elif self.crossref and self.crossref.notes:
            return self.crossref.notes
        elif self.arxiv and self.arxiv.notes:
            return self.arxiv.notes
        elif self.repec and self.repec.notes:
            return self.repec.notes
        elif self.dblp and self.dblp.notes:
            return self.dblp.notes
        elif self.dblp and self.manual.notes:
            return self.manual.notes
        else: return ''

    @property
    def conference_start(self):
        '''wrapper arond field that chooses that prefered source'''
        if self.wos and self.wos.conference_start:
            return self.wos.conference_start
        elif self.scopus and self.scopus.conference_start:
            return self.scopus.conference_start
        elif self.pubmed and self.pubmed.conference_start:
            return self.pubmed.conference_start
        elif self.crossref and self.crossref.conference_start:
            return self.crossref.conference_start
        elif self.arxiv and self.arxiv.conference_start:
            return self.arxiv.conference_start
        elif self.repec and self.repec.conference_start:
            return self.repec.conference_start
        elif self.dblp and self.dblp.conference_start:
            return self.dblp.conference_start
        elif self.dblp and self.manual.conference_start:
            return self.manual.conference_start
        else: return ''

    @property
    def conference_end(self):
        '''wrapper arond field that chooses that prefered source'''
        if self.wos and self.wos.conference_end:
            return self.wos.conference_end
        elif self.scopus and self.scopus.conference_end:
            return self.scopus.conference_end
        elif self.pubmed and self.pubmed.conference_end:
            return self.pubmed.conference_end
        elif self.crossref and self.crossref.conference_end:
            return self.crossref.conference_end
        elif self.arxiv and self.arxiv.conference_end:
            return self.arxiv.conference_end
        elif self.repec and self.repec.conference_end:
            return self.repec.conference_end
        elif self.dblp and self.dblp.conference_end:
            return self.dblp.conference_end
        elif self.dblp and self.manual.conference_end:
            return self.manual.conference_end
        else: return ''

    @property
    def conference_name(self):
        '''wrapper arond field that chooses that prefered source'''
        if self.wos and self.wos.conference_name:
            return self.wos.conference_name
        elif self.scopus and self.scopus.conference_name:
            return self.scopus.conference_name
        elif self.pubmed and self.pubmed.conference_name:
            return self.pubmed.conference_name
        elif self.crossref and self.crossref.conference_name:
            return self.crossref.conference_name
        elif self.arxiv and self.arxiv.conference_name:
            return self.arxiv.conference_name
        elif self.repec and self.repec.conference_name:
            return self.repec.conference_name
        elif self.dblp and self.dblp.conference_name:
            return self.dblp.conference_name
        elif self.dblp and self.manual.conference_name:
            return self.manual.conference_name
        else: return ''

    @property
    def conference_place(self):
        '''wrapper arond field that chooses that prefered source'''
        if self.wos and self.wos.conference_place:
            return self.wos.conference_place
        elif self.scopus and self.scopus.conference_place:
            return self.scopus.conference_place
        elif self.pubmed and self.pubmed.conference_place:
            return self.pubmed.conference_place
        elif self.crossref and self.crossref.conference_place:
            return self.crossref.conference_place
        elif self.arxiv and self.arxiv.conference_place:
            return self.arxiv.conference_place
        elif self.repec and self.repec.conference_place:
            return self.repec.conference_place
        elif self.dblp and self.dblp.conference_place:
            return self.dblp.conference_place
        elif self.dblp and self.manual.conference_place:
            return self.manual.conference_place
        else: return ''

    @property
    def acceptance_date(self):
        '''wrapper arond field that chooses that prefered source'''
        if self.wos and self.wos.acceptance_date:
            return self.wos.acceptance_date
        elif self.scopus and self.scopus.acceptance_date:
            return self.scopus.acceptance_date
        elif self.pubmed and self.pubmed.acceptance_date:
            return self.pubmed.acceptance_date
        elif self.crossref and self.crossref.acceptance_date:
            return self.crossref.acceptance_date
        elif self.arxiv and self.arxiv.acceptance_date:
            return self.arxiv.acceptance_date
        elif self.repec and self.repec.acceptance_date:
            return self.repec.acceptance_date
        elif self.dblp and self.dblp.acceptance_date:
            return self.dblp.acceptance_date
        elif self.dblp and self.manual.acceptance_date:
            return self.manual.acceptance_date
        else: return ''

    @property
    def book_title(self):
        '''wrapper arond field that chooses that prefered source'''
        if self.wos and self.wos.book_title:
            return self.wos.book_title
        elif self.scopus and self.scopus.book_title:
            return self.scopus.book_title
        elif self.pubmed and self.pubmed.book_title:
            return self.pubmed.book_title
        elif self.crossref and self.crossref.book_title:
            return self.crossref.book_title
        elif self.arxiv and self.arxiv.book_title:
            return self.arxiv.book_title
        elif self.repec and self.repec.book_title:
            return self.repec.book_title
        elif self.dblp and self.dblp.book_title:
            return self.dblp.book_title
        elif self.dblp and self.manual.book_title:
            return self.manual.book_title
        else: return ''

    @property
    def series(self):
        '''wrapper arond field that chooses that prefered source'''
        if self.wos and self.wos.series:
            return self.wos.series
        elif self.scopus and self.scopus.series:
            return self.scopus.series
        elif self.pubmed and self.pubmed.series:
            return self.pubmed.series
        elif self.crossref and self.crossref.series:
            return self.crossref.series
        elif self.arxiv and self.arxiv.series:
            return self.arxiv.series
        elif self.repec and self.repec.series:
            return self.repec.series
        elif self.dblp and self.dblp.series:
            return self.dblp.series
        elif self.dblp and self.manual.series:
            return self.manual.series
        else: return ''

    @property
    def edition(self):
        '''wrapper arond field that chooses that prefered source'''
        if self.wos and self.wos.edition:
            return self.wos.edition
        elif self.scopus and self.scopus.edition:
            return self.scopus.edition
        elif self.pubmed and self.pubmed.edition:
            return self.pubmed.edition
        elif self.crossref and self.crossref.edition:
            return self.crossref.edition
        elif self.arxiv and self.arxiv.edition:
            return self.arxiv.edition
        elif self.repec and self.repec.edition:
            return self.repec.edition
        elif self.dblp and self.dblp.edition:
            return self.dblp.edition
        elif self.dblp and self.manual.edition:
            return self.manual.edition
        else: return ''

    @property
    def relationship(self):
        '''wrapper arond field that chooses that prefered source'''
        if self.wos and self.wos.relationship:
            return self.wos.relationship
        elif self.scopus and self.scopus.relationship:
            return self.scopus.relationship
        elif self.pubmed and self.pubmed.relationship:
            return self.pubmed.relationship
        elif self.crossref and self.crossref.relationship:
            return self.crossref.relationship
        elif self.arxiv and self.arxiv.relationship:
            return self.arxiv.relationship
        elif self.repec and self.repec.relationship:
            return self.repec.relationship
        elif self.dblp and self.dblp.relationship:
            return self.dblp.relationship
        elif self.dblp and self.manual.relationship:
            return self.manual.relationship
        else: return ''

    @property
    def medium(self):
        '''wrapper arond field that chooses that prefered source'''
        if self.wos and self.wos.medium:
            return self.wos.medium
        elif self.scopus and self.scopus.medium:
            return self.scopus.medium
        elif self.pubmed and self.pubmed.medium:
            return self.pubmed.medium
        elif self.crossref and self.crossref.medium:
            return self.crossref.medium
        elif self.arxiv and self.arxiv.medium:
            return self.arxiv.medium
        elif self.repec and self.repec.medium:
            return self.repec.medium
        elif self.dblp and self.dblp.medium:
            return self.dblp.medium
        elif self.dblp and self.manual.medium:
            return self.manual.medium
        else: return ''

    @property
    def num_chapters(self):
        '''wrapper arond field that chooses that prefered source'''
        if self.wos and self.wos.num_chapters:
            return self.wos.num_chapters
        elif self.scopus and self.scopus.num_chapters:
            return self.scopus.num_chapters
        elif self.pubmed and self.pubmed.num_chapters:
            return self.pubmed.num_chapters
        elif self.crossref and self.crossref.num_chapters:
            return self.crossref.num_chapters
        elif self.arxiv and self.arxiv.num_chapters:
            return self.arxiv.num_chapters
        elif self.repec and self.repec.num_chapters:
            return self.repec.num_chapters
        elif self.dblp and self.dblp.num_chapters:
            return self.dblp.num_chapters
        elif self.dblp and self.manual.num_chapters:
            return self.manual.num_chapters
        else: return ''

    @property
    def pub_place(self):
        '''wrapper arond field that chooses that prefered source'''
        if self.wos and self.wos.pub_place:
            return self.wos.pub_place
        elif self.scopus and self.scopus.pub_place:
            return self.scopus.pub_place
        elif self.pubmed and self.pubmed.pub_place:
            return self.pubmed.pub_place
        elif self.crossref and self.crossref.pub_place:
            return self.crossref.pub_place
        elif self.arxiv and self.arxiv.pub_place:
            return self.arxiv.pub_place
        elif self.repec and self.repec.pub_place:
            return self.repec.pub_place
        elif self.dblp and self.dblp.pub_place:
            return self.dblp.pub_place
        elif self.dblp and self.manual.pub_place:
            return self.manual.pub_place
        else: return ''

    @property
    def pub_url(self):
        '''wrapper arond field that chooses that prefered source'''
        if self.wos and self.wos.pub_url:
            return self.wos.pub_url
        elif self.scopus and self.scopus.pub_url:
            return self.scopus.pub_url
        elif self.pubmed and self.pubmed.pub_url:
            return self.pubmed.pub_url
        elif self.crossref and self.crossref.pub_url:
            return self.crossref.pub_url
        elif self.arxiv and self.arxiv.pub_url:
            return self.arxiv.pub_url
        elif self.repec and self.repec.pub_url:
            return self.repec.pub_url
        elif self.dblp and self.dblp.pub_url:
            return self.dblp.pub_url
        elif self.dblp and self.manual.pub_url:
            return self.manual.pub_url
        else: return ''

    @property
    def isbn10(self):
        '''wrapper arond field that chooses that prefered source'''
        if self.wos and self.wos.isbn10:
            return self.wos.isbn10
        elif self.scopus and self.scopus.isbn10:
            return self.scopus.isbn10
        elif self.pubmed and self.pubmed.isbn10:
            return self.pubmed.isbn10
        elif self.crossref and self.crossref.isbn10:
            return self.crossref.isbn10
        elif self.arxiv and self.arxiv.isbn10:
            return self.arxiv.isbn10
        elif self.repec and self.repec.isbn10:
            return self.repec.isbn10
        elif self.dblp and self.dblp.isbn10:
            return self.dblp.isbn10
        elif self.dblp and self.manual.isbn10:
            return self.manual.isbn10
        else: return ''

    @property
    def chapter_num(self):
        '''wrapper arond field that chooses that prefered source'''
        if self.wos and self.wos.chapter_num:
            return self.wos.chapter_num
        elif self.scopus and self.scopus.chapter_num:
            return self.scopus.chapter_num
        elif self.pubmed and self.pubmed.chapter_num:
            return self.pubmed.chapter_num
        elif self.crossref and self.crossref.chapter_num:
            return self.crossref.chapter_num
        elif self.arxiv and self.arxiv.chapter_num:
            return self.arxiv.chapter_num
        elif self.repec and self.repec.chapter_num:
            return self.repec.chapter_num
        elif self.dblp and self.dblp.chapter_num:
            return self.dblp.chapter_num
        elif self.dblp and self.manual.chapter_num:
            return self.manual.chapter_num
        else: return ''

    @property
    def isbn13(self):
        '''wrapper arond field that chooses that prefered source'''
        if self.wos and self.wos.isbn13:
            return self.wos.isbn13
        elif self.scopus and self.scopus.isbn13:
            return self.scopus.isbn13
        elif self.pubmed and self.pubmed.isbn13:
            return self.pubmed.isbn13
        elif self.crossref and self.crossref.isbn13:
            return self.crossref.isbn13
        elif self.arxiv and self.arxiv.isbn13:
            return self.arxiv.isbn13
        elif self.repec and self.repec.isbn13:
            return self.repec.isbn13
        elif self.dblp and self.dblp.isbn13:
            return self.dblp.isbn13
        elif self.dblp and self.manual.isbn13:
            return self.manual.isbn13
        else: return ''

    @property
    def author_url(self):
        '''wrapper arond field that chooses that prefered source'''
        if self.wos and self.wos.author_url:
            return self.wos.author_url
        elif self.scopus and self.scopus.author_url:
            return self.scopus.author_url
        elif self.pubmed and self.pubmed.author_url:
            return self.pubmed.author_url
        elif self.crossref and self.crossref.author_url:
            return self.crossref.author_url
        elif self.arxiv and self.arxiv.author_url:
            return self.arxiv.author_url
        elif self.repec and self.repec.author_url:
            return self.repec.author_url
        elif self.dblp and self.dblp.author_url:
            return self.dblp.author_url
        elif self.dblp and self.manual.author_url:
            return self.manual.author_url
        else: return ''

    @property
    def author_address(self):
        '''wrapper arond field that chooses that prefered source'''
        if self.wos and self.wos.author_address:
            return self.wos.author_address
        elif self.scopus and self.scopus.author_address:
            return self.scopus.author_address
        elif self.pubmed and self.pubmed.author_address:
            return self.pubmed.author_address
        elif self.crossref and self.crossref.author_address:
            return self.crossref.author_address
        elif self.arxiv and self.arxiv.author_address:
            return self.arxiv.author_address
        elif self.repec and self.repec.author_address:
            return self.repec.author_address
        elif self.dblp and self.dblp.author_address:
            return self.dblp.author_address
        elif self.dblp and self.manual.author_address:
            return self.manual.author_address
        else: return ''

    @property
    def confidential(self):
        '''wrapper arond field that chooses that prefered source'''
        if self.wos and self.wos.confidential:
            return self.wos.confidential
        elif self.scopus and self.scopus.confidential:
            return self.scopus.confidential
        elif self.pubmed and self.pubmed.confidential:
            return self.pubmed.confidential
        elif self.crossref and self.crossref.confidential:
            return self.crossref.confidential
        elif self.arxiv and self.arxiv.confidential:
            return self.arxiv.confidential
        elif self.repec and self.repec.confidential:
            return self.repec.confidential
        elif self.dblp and self.dblp.confidential:
            return self.dblp.confidential
        elif self.dblp and self.manual.confidential:
            return self.manual.confidential
        else: return ''

    @property
    def sponsor(self):
        '''wrapper arond field that chooses that prefered source'''
        if self.wos and self.wos.sponsor:
            return self.wos.sponsor
        elif self.scopus and self.scopus.sponsor:
            return self.scopus.sponsor
        elif self.pubmed and self.pubmed.sponsor:
            return self.pubmed.sponsor
        elif self.crossref and self.crossref.sponsor:
            return self.crossref.sponsor
        elif self.arxiv and self.arxiv.sponsor:
            return self.arxiv.sponsor
        elif self.repec and self.repec.sponsor:
            return self.repec.sponsor
        elif self.dblp and self.dblp.sponsor:
            return self.dblp.sponsor
        elif self.dblp and self.manual.sponsor:
            return self.manual.sponsor
        else: return ''

    @property
    def issn(self):
        '''wrapper arond field that chooses that prefered source'''
        if self.wos and self.wos.issn:
            return self.wos.issn
        elif self.scopus and self.scopus.issn:
            return self.scopus.issn
        elif self.pubmed and self.pubmed.issn:
            return self.pubmed.issn
        elif self.crossref and self.crossref.issn:
            return self.crossref.issn
        elif self.arxiv and self.arxiv.issn:
            return self.arxiv.issn
        elif self.repec and self.repec.issn:
            return self.repec.issn
        elif self.dblp and self.dblp.issn:
            return self.dblp.issn
        elif self.dblp and self.manual.issn:
            return self.manual.issn
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
        elif self.dblp and self.manual.language:
            return self.manual.language
        else: lang = ''


        nodes = langs.node.xpath("//lang:language[lang:name='%s' or lang:code='%s']" % (lang, lang), namespaces=ns)
        if nodes:
            return (nodes[0].findtext('lang:code', namespaces=ns), nodes[0].findtext('lang:name', namespaces=ns))

        else:
            return ('', '')

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
        elif self.dblp and self.manual.abstract:
            return self.manual.abstract
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
        elif self.dblp and self.manual.volume:
            return self.manual.volume
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
        elif self.dblp and self.manual.issue:
            return self.manual.issue
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
        elif self.dblp and self.manual.pubdate:
            return self.manual.pubdate
        else: return False

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
        elif self.dblp and self.manual.pages:
            return self.manual.pages
        else: return False


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
        elif self.dblp and self.manual.publisher:
            return self.manual.publisher
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
        elif self.dblp and self.manual.journal:
            return self.manual.journal
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
        elif self.dblp and self.manual.doi:
            return self.manual.doi
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
        elif self.dblp and self.manual.keywords:
            return self.manual.keywords
        else: return [] # empty keywords

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
    manual = xmlmap.NodeField("atom:entry[pubs:data-source/pubs:source-name='manual-entry']", SympSource)

