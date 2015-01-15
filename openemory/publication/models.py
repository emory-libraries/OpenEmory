# file openemory/publication/models.py
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

import logging
import os

from collections import defaultdict
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.db import models
from django.template import Context
from django.template.defaultfilters import slugify
from django.template.loader import get_template
from django.utils.safestring import mark_safe
from eulfedora.models import DigitalObject, FileDatastream, \
     XmlDatastream, RdfDatastream, Relation
from eulfedora.util import RequestFailed, parse_rdf
#from eulfedora.indexdata.util import pdf_to_text
from openemory.util import pdf_to_text
from eulfedora.rdfns import relsext, oai
from eulfedora.rdfns import model as relsextns
from eullocal.django.emory_ldap.backends import EmoryLDAPBackend
from eulxml import xmlmap
from eulxml.xmlmap import mods, premis, fields as xmlfields
from lxml import etree
from pyPdf import PdfFileReader, PdfFileWriter
from rdflib.graph import Graph as RdfGraph, Namespace
from rdflib import URIRef, RDF, RDFS, Literal
from rdflib.namespace import ClosedNamespace
import subprocess
from cStringIO import StringIO
import subprocess
import tempfile
import time
from xhtml2pdf import pisa

import openemory
from openemory.common.fedora import DigitalObject
from openemory.rdfns import DC, BIBO, FRBR, ns_prefixes
from openemory.util import pmc_access_url
from openemory.util import solr_interface
from openemory.publication.symp import SympAtom

logger = logging.getLogger(__name__)

# Define Special options for embargo duration 
NO_LIMIT = {"value":"Indefinite", "display":"Indefinite"}
UNKNOWN_LIMIT = {"value":"Not Known", "display":"Unknown"}

class TypedRelatedItem(mods.RelatedItem):

    def is_empty(self):
        """Returns True if all fields are empty, and no attributes
        other than **type** or **displayLabel**. False if any fields
        are not empty."""

        # ignore these fields when checking if a related item is empty
        ignore = ['type', 'label']  # type and displayLabel attributes

        for name in self._fields.iterkeys():
            if name in ignore:
                continue
            f = getattr(self, name)
            # if this is an XmlObject or NodeListField with an
            # is_empty method, rely on that
            if hasattr(f, 'is_empty'):
                if not f.is_empty():
                    return False
            # if this is a list or value field (int, string), check if empty
            elif not (f is None or f == '' or f == []):
                return False

        # no non-empty non-ignored fields were found - return True
        return True

class JournalMods(TypedRelatedItem):
    publisher = xmlmap.StringField('mods:originInfo/mods:publisher', required=True)
    issn = xmlmap.StringField('mods:identifier[@type="issn"]')
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

class ResearchField(mods.Subject):
    def __init__(self, *args, **kwargs):
        super(ResearchField, self).__init__(*args, **kwargs)
        self.authority = 'proquestresearchfield'

class FinalVersion(TypedRelatedItem):
    url = xmlmap.StringField('mods:identifier[@type="uri"][@displayLabel="URL"]',
                             required=False)
    doi = xmlmap.StringField('mods:identifier[@type="doi"][@displayLabel="DOI"]',
                             required=False)

class SupplementalMaterial(TypedRelatedItem):
    xlink_ns = 'http://www.w3.org/1999/xlink'
    ROOT_NAMESPACES = {'xlink': xlink_ns}

    url = xmlmap.StringField('@xlink:href', required=False)

    def __init__(self, *args, **kwargs):
        super(SupplementalMaterial, self).__init__(*args, **kwargs)
        self.type='references'
        self.label='SupplementalMaterial'


class MODSLicense(xmlmap.XmlObject):
    ROOT_NAME = 'license'
    xlink_ns = 'http://www.w3.org/1999/xlink'
    ROOT_NAMESPACES = {'xlink': xlink_ns}
    link = xmlmap.StringField('@xlink:href')
    text = xmlmap.StringField('text()')

    @property
    def is_creative_commons(self):
        '''
        Wraper function for :meth:`~_is_creative_commons`
        indicates if the license is recognized as a
        Creative Commons license, based on the URL in the license
        '''
        return _is_creative_commons(self.link)

    @property
    def cc_type(self):
        '''
        Wraper function for :meth:`~_cc_type`
        short name for the type of Creative Commons license (e.g.,
    ``by`` or ``by-nd``), if this license is a Creative Commons
    license.
        '''
        return _cc_type(self.link)

class MODSCopyright(xmlmap.XmlObject):
    ROOT_NAME = 'copyright'
    text = xmlmap.StringField('text()')

    def is_empty(self):
        '''Returns False unless a text is populated'''
        return not bool(self.text)

class MODSAdminNote(xmlmap.XmlObject):
    ROOT_NAME = 'adminNote'
    text = xmlmap.StringField('text()')

    def is_empty(self):
        '''Returns False unless a text is populated'''
        return not bool(self.text)

class ArticleMods(mods.MODSv34):
    ark = xmlmap.StringField('mods:identifier[@type="ark"]')
    'short for of object ARK'
    license = xmlmap.NodeField('mods:accessCondition[@type="use and reproduction"][@displayLabel="license"]', MODSLicense)
    'License information'
    copyright =xmlmap.NodeField('mods:accessCondition[@type="use and reproduction"][@displayLabel="copyright"]', MODSCopyright)
    'copyright statement'
    admin_note =xmlmap.NodeField('mods:accessCondition[@type="restrictions on access"][@displayLabel="RightsNote"]', MODSAdminNote)
    'Admin note for record exceptions and non-standard permissions'
    rights_research_date =xmlmap.StringField('mods:accessCondition[@type="restrictions on access"][@displayLabel="copyrightStatusDeterminationDate"]')
    'Date rights research was conducted'
    ark_uri = xmlmap.StringField('mods:identifier[@type="uri"]')
    'full ARK of object'
    authors = xmlmap.NodeListField('mods:name[@type="personal"][mods:role/mods:roleTerm="author"]', AuthorName)
    funders = xmlmap.NodeListField('mods:name[@type="corporate"][mods:role/mods:roleTerm="funder"]',
                               FundingGroup, verbose_name='Funding Group or Granting Agency')
    'external funding group or granting agency supporting research for the article'
    journal = xmlmap.NodeField('mods:relatedItem[@type="host"]',
                               JournalMods)
    'information about the journal where the article was published'
    author_notes = xmlmap.NodeListField('mods:note[@type="author notes"]',
                                        AuthorNote)
    keywords = xmlmap.NodeListField('mods:subject[@authority="keywords"]',
                                   Keyword)
    subjects = xmlmap.NodeListField('mods:subject[@authority="proquestresearchfield"]',
                                   ResearchField)
    genre = xmlmap.StringField('mods:genre[@authority="marcgt"]')
    version = xmlmap.StringField('mods:genre[@authority="local"]',
                                 choices=['', 'Preprint: Prior to Peer Review',
                                          'Post-print: After Peer Review',
                                          'Final Publisher PDF',
                                     ],
                                 help_text='''Preprint: Draft, pre-refereeing.  Version of the paper initially
                                 submitted to a journal publisher.  Post-Print:  Final draft, post-refereeing.
                                 Version of the paper including changes made in response to peer review.  Final
                                 Publisher's Version/PDF:  Version of the paper with copy editing and formatting done
                                 by the editor or journal publisher.''')
    'version of the article being submitted (e.g., preprint, post-print, etc)'
    publication_date = xmlmap.StringField('mods:originInfo/mods:dateIssued[@encoding="w3cdtf"][@keyDate="yes"]')
    final_version = xmlmap.NodeField('mods:relatedItem[@type="otherVersion"][@displayLabel="Final Published Version"]',
                                     FinalVersion)
    # convenience mappings for language code & text value
    language_code = xmlmap.StringField('mods:language/mods:languageTerm[@type="code"][@authority="iso639-2b"]')
    language = xmlmap.StringField('mods:language/mods:languageTerm[@type="text"]')

    # embargo information
    _embargo = xmlmap.StringField('mods:accessCondition[@type="restrictionOnAccess"]')
    embargo_end = xmlmap.StringField('mods:originInfo/mods:dateOther[@type="embargoedUntil"][@encoding="w3cdtf"]')

    supplemental_materials = xmlmap.NodeListField('mods:relatedItem[@type="references"][@displayLabel="SupplementalMaterial"]', SupplementalMaterial)
    'link to external supplemental material'

    _embargo_prefix = 'Embargoed for '
    def _get_embargo(self):
        if self._embargo:
            return self._embargo[len(self._embargo_prefix):]
    def _set_embargo(self, value):
        if value is None:
            del self._embargo
        else:
            # if the value is set to "No embargo" do not add _embargo_prefix
            if slugify(value) == slugify("No embargo"):
                self._embargo = value
            else:
                self._embargo = '%s%s' % (self._embargo_prefix, value)
    def _del_embargo(self):
        del self._embargo 
        
    embargo = property(_get_embargo, _set_embargo, _del_embargo,
        '''Embargo duration.  Stored internally as "Embargoed for xx"
        in ``mods:accessCondition[@type="restrictionOnAccess"], but should be accessed
        and updated via this attribute with just the duration value.''')

    def calculate_embargo_end(self):
        '''Calculate and store an embargo end date in
        :attr:`embargo_end` based on the embargo duration set in
        :attr:`embargo`.

        The embargo is calculated relative to the publication date set
        in :attr:`publication_date` if set.  If the date is year or
        year-month only, embargo will be calculated from the first day
        of the next year or month (e.g., for a publication date of
        2012, the embargo will be calculated from 2013-01-01.)
        '''
        if not self.embargo:
            # no embargo duration is set - nothing to calculate
            # make sure embargo end date is not set
            del self.embargo_end
            return

        if not self.publication_date:
            # publication date is required and should be set by the
            # time of calculation; if not set, just bail out
            return
        
        if slugify(self.embargo) == slugify(NO_LIMIT["value"]):
            self.embargo_end = NO_LIMIT["value"]
            return
            
        if slugify(self.embargo) == slugify(UNKNOWN_LIMIT["value"]):
            self.embargo_end = UNKNOWN_LIMIT["value"]
            return
        
        # parse publication date and convert to a datetime.date
        date_parts = self.publication_date.split('-')
        
        # handle year only, year-month, or year-month day
        year = int(date_parts[0])
        adjustment = {}  # possible adjustment for partial dates
        # check for month
        if len(date_parts) > 1:
            month = int(date_parts[1])

            # check for day
            if len(date_parts) > 2:
                day = int(date_parts[2])
            else:
                # no day specified - use the first day of the next month
                adjustment['months'] = 1
                day = 1

        # no month specified - use the first day of the next year
        else:
            adjustment['years'] = 1
            month = day = 1
                
        relative_to = date(year, month, day) + relativedelta(**adjustment)
        
        try:
          # generate a relativedelta based on embargo duration

          num, unit = slugify(self.embargo).split('-')

          if not unit.endswith('s'):
              unit += 's'
          delta_info = {unit: int(num)}
          duration = relativedelta(**delta_info)

          embargo_end = relative_to + duration
          self.embargo_end = embargo_end.isoformat()
        except:
          return slugify(self.embargo_end)

class NlmAuthor(xmlmap.XmlObject):
    '''Minimal wrapper for author in NLM XML'''
    surname = xmlmap.StringField('name/surname')
    '''author surname'''
    given_names = xmlmap.StringField('name/given-names')
    '''author given name(s)'''
    email = xmlmap.StringField('email')
    '''author email, or None if missing'''
    aff_ids = xmlmap.StringListField('xref[@ref-type="aff"]/@rid')
    aff = xmlmap.StringField('aff')

    @property
    def affiliation(self):
        '''author institutional affiliation, or None if missing'''
        # affiliation tag inside author name
        if self.aff:
            return self.aff

        # if affiliation xreference ids are present, look them up
        if self.aff_ids:
            # an author could have multiple affiliations; just put
            # them all into one text field for now
            aff = ''
            for aid in self.aff_ids:
                # find the affiliation id by the xref and return the
                # contents
                # TODO: remove label from text ? 
                aff += self.node.xpath('normalize-space(string(ancestor::front//aff[@id="%s"]))' \
                                       % aid)
            return aff

class NlmFootnote(xmlmap.XmlObject):
    type = xmlmap.StringField('@fn-type')
    id = xmlmap.StringField('@id')
    label = xmlmap.StringField('label')
    p = xmlmap.StringListField('p', normalize=True)
                               

class NlmAuthorNotes(xmlmap.XmlObject):
    corresp = xmlmap.StringField('corresp', normalize=True)
    fn = xmlmap.NodeListField('fn', NlmFootnote)

    @property
    def notes(self):
        n = []
        if self.corresp:
            n.append(unicode(self.corresp))
        n.extend([unicode(fn) for fn in self.fn])
        return n

class NlmPubDate(xmlmap.XmlObject):
    '''Publication date in NLM XML'''
    ROOT_NAME = 'pub-date'
    type = xmlmap.StringField('@pub-type')
    day = xmlmap.IntegerField('day')
    month = xmlmap.IntegerField('month')
    year = xmlmap.IntegerField('year')
    # could also have a "season" (e.g., Spring, Third Quarter)
    # year is required but day and month are optional

    def __unicode__(self):
        date = '%s' % self.year
        if self.month:
            date += '-%02d' % self.month
            if self.day:
                date += '-%02d' % self.day
        return date

class NlmSection(xmlmap.XmlObject):
    '''A group of material with a heading; a section of an article'''
    ROOT_NAME = 'sec'
    title = xmlmap.StringField('title') 
    paragraphs = xmlmap.StringListField('p', normalize=True) # zero or more
    # minimal sections mapping for abstracts; can have other fields,
    # but we don't expect them in an abstract

    def __unicode__(self):
        text = ''
        if self.title:
            text = '%s\n' % self.title
        if self.paragraphs:
            text += '\n'.join(self.paragraphs)
        return text

class NlmAbstract(xmlmap.XmlObject):
    ROOT_NAME = 'abstract'
    label = xmlmap.StringField('label') # zero or one
    title = xmlmap.StringField('title') # zero or one
    paragraphs = xmlmap.StringListField('p', normalize=True) # zero or more
    sections = xmlmap.NodeListField('sec', NlmSection) # zero or more

    def __unicode__(self):
        '''Convert abstract to plain-text, preserving sections and
        headers where possible with line-breaks.'''
        text = ''
        if self.label:
            text = '%s\n' % self.label
        if self.title:
            text += '%s\n' % self.title
        if self.paragraphs:
            text += '\n'.join(self.paragraphs)
        if self.sections:
            text += '\n\n'.join(unicode(sec) for sec in self.sections)
        return text

_cc_prefix = 'http://creativecommons.org/licenses/'
_pd_prefix = 'http://creativecommons.org/publicdomain/'

def _is_creative_commons(url):
        '''
        :param url: url of the license
        :type boolean: indicates if the license is recognized as a
        Creative Commons license, based on the URL in the license
        xlink:href attribute, if any.

        .. Note::

          Currently only recognizes articles that link directly to a
          Creative Commons license.
        '''
        return url and (url.startswith(_cc_prefix) or url.startswith(_pd_prefix))

def _cc_type(url):
    '''
    :param url: url of the license
    Short name for the type of Creative Commons license (e.g.,
    ``by`` or ``by-nd``), if this license is a Creative Commons
    license.'''
    if _is_creative_commons(url):
        if url.startswith(_cc_prefix):
            license_type = url[len(_cc_prefix):]
        elif url.startswith(_pd_prefix):
            license_type = url[len(_pd_prefix):]
        return license_type[:license_type.find('/')]

class NlmLicense(xmlmap.XmlObject):
    ROOT_NAME = 'license'
    xlink_ns = 'http://www.w3.org/1999/xlink'
    ROOT_NAMESPACES = {'xlink': xlink_ns}

    type = xmlmap.StringField('@license-type')
    'license type (``@license-type``)'
    link = xmlmap.StringField('@xlink:href|.//@xlink:href')
    'license link (``@xlink:href`` or the first xlink:href within the license content)'

    _text = None
    @property
    def text(self):
        '''Plain text of the license content, including any link urls.'''
        if self._text is None:
            txt = []
            # iterate through node children in serialization order
            for el in self.node.iter():
                # for now, skip comments & processing instructions
                if isinstance(el.tag, basestring):
                    if el.text:
                        txt.append(el.text)
                        
                    if el.tag in ['ext-link', 'uri'] and not el.text:
                        # NOTE: of link has text other than the uri,
                        # uri will not be displayed anywhere in plain-text version
                        txt.append(el.attrib['{%s}href' % self.xlink_ns])
                        
                # any element (including a comment) could have tail content
                if el.tail:
                    txt.append(el.tail)
                        
            self._text =  ''.join(txt)
                
        return self._text

    _html = None
    @property
    def html(self):
        '''HTML version of the license content, with embedded
        ``ext-links`` or ``uri`` converted to as HTML links.'''
        # NOTE: some overlap in logic with text property
        if self._html is None:
            html = []
            # iterate through node children in serialization order
            for el in self.node.iter():
                # for now, skip comments & processing instructions
                if isinstance(el.tag, basestring):
                    # special handling for links
                    if el.tag in ['ext-link', 'uri']:
                        link = el.attrib['{%s}href' % self.xlink_ns]
                        link_text = el.text or link
                        html.append('<a href="%s">%s</a>' % (link, link_text))
                        
                    elif el.text:
                        html.append(el.text)

                # any element (including a comment) could have tail content
                if el.tail:
                    html.append(el.tail)
                        
            self._html =  mark_safe(''.join(html))
                
        return self._html


    def __unicode__(self):
        return self.text

    
    @property
    def is_creative_commons(self):
        '''
        Wraper function for :meth:`~_is_creative_commons`
        indicates if the license is recognized as a
        Creative Commons license, based on the URL in the license
        '''
        return _is_creative_commons(self.link)

    @property
    def cc_type(self):
        '''
        Wraper function for :meth:`~_cc_type`
        short name for the type of Creative Commons license (e.g.,
    ``by`` or ``by-nd``), if this license is a Creative Commons
    license.
        '''
        return _cc_type(self.link)




class NlmArticle(xmlmap.XmlObject):
    '''Minimal wrapper for NLM XML article'''
    ROOT_NAME = 'article'

    docid = xmlmap.IntegerField('front/article-meta/' +
            'article-id[@pub-id-type="pmc"]')
    '''PMC document id from :class:`ESearchResponse`; *not* PMID'''
    pmid = xmlmap.IntegerField('front/article-meta/' +
            'article-id[@pub-id-type="pmid"]')
    '''PubMed id of the article'''
    doi = xmlmap.StringField('front/article-meta/' +
            'article-id[@pub-id-type="doi"]')
    '''Digital Object Identifier (DOI) for the article'''
    journal_title = xmlmap.StringField('front/journal-meta/journal-title|front/journal-meta/journal-title-group/journal-title')
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
    abstract = xmlmap.NodeField('front/article-meta/abstract', NlmAbstract)
    '''article abstract'''
    body = xmlmap.NodeField('body', xmlmap.XmlObject)
    '''preliminary mapping to article body (currently used to
    determine when full-text of the article is available)'''
    sponsors = xmlmap.StringListField('front/article-meta/contract-sponsor')
    '''Sponsor or funding group'''
    volume = xmlmap.StringField('front/article-meta/volume')
    'journal volume'
    issue = xmlmap.StringField('front/article-meta/issue')
    'journal issue'
    first_page = xmlmap.StringField('front/article-meta/fpage')
    'first page'
    last_page = xmlmap.StringField('front/article-meta/lpage')
    'last page'
    publisher = xmlmap.StringField('front/journal-meta/publisher/publisher-name')
    'journal publisher'
    pubdates = xmlmap.NodeListField('front/article-meta/pub-date',
                                     NlmPubDate)
    '''Article publication dates as list of :class:`NlmPubDate`.'''
    pubdate_types = xmlmap.StringListField('front/article-meta/pub-date/@pub-type')
    # publication date types, for selecting first-choice pubdate
    keywords = xmlmap.StringListField('front/article-meta/kwd-group/kwd')
    '''keywords describing the content of the article'''
    author_notes = xmlmap.NodeListField('front/article-meta/author-notes',
                                        NlmAuthorNotes)
    copyright = xmlmap.StringField('front/article-meta/permissions/copyright-statement')
    license = xmlmap.NodeField('front/article-meta/permissions/license', NlmLicense)


    _publication_date = None
    @property
    def publication_date(self):
        '''Article publication date as :class:`NlmPubDate`.  Looks for the
        article pub-date by type, and takes the first available of these,
        in this order: `epub-ppub` (both epub and ppub dates), `ppub`
        (print publication), `epub` (electronic publication).'''
        if self._publication_date is None:
            # pub-date types, in the order of preference
            pubdatetypes = ['epub-ppub', 'ppub', 'epub']
            # determine which type we should use
            for pdtype in pubdatetypes:
                if pdtype in self.pubdate_types:
                    type = pdtype
                    break
            # find the right pubdate
            for pd in self.pubdates:
                if pd.type == type:
                    self._publication_date = pd
                    
        return self._publication_date

    @property
    def fulltext_available(self):
        '''boolean; indicates whether or not the full text of the
        article is included in the fetched article.'''
        return self.body != None

    _identified_authors = None
    def identifiable_authors(self, refresh=False, derive=False):
        '''Identify any Emory authors for the article and, if
        possible, return a list of corresponding
        :class:`~django.contrib.auth.models.User` objects.
        If derive is True it will try harder to match,
        it will try to derive based on netid and name.

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
                    user_dn, user = ldap.find_user_by_email(em, derive)
                    if user:
                        self._identified_authors.append(user)

        return self._identified_authors

    def as_article_mods(self):
        amods = ArticleMods()
        # title & subtitle
        amods.create_title_info()
        amods.title_info.title = self.article_title
        amods.title_info.subtitle = self.article_subtitle
        # author names
        id_auths = self.identifiable_authors()
        # generate a dict of email -> username for identified emory authors
        author_ids = {}
        for author_user in id_auths:
            author_ids[author_user.email] = author_user.username
        
        for auth in self.authors:
            modsauth = AuthorName(family_name=auth.surname,
                                           given_name=auth.given_names)

            # standardize any Emory affiliation
            if auth.affiliation:
                if 'Emory University' in auth.affiliation:
                    modsauth.affiliation = 'Emory University'
                else:
                    modsauth.affiliation = auth.affiliation

            # if author has an email and it matches a name we
            # identified, set the username as mods id
            if auth.email in author_ids:
                modsauth.id = author_ids[auth.email]
            else:
                # in some cases, corresponding email is not linked to
                # author name - do a best-guess match
                for idauth in id_auths:
                    # if last name matches and first name is in given name
                    # (may have an extra initial, etc.), consider it a match
                    if auth.surname == idauth.last_name and \
                           idauth.first_name in auth.given_names:
                        modsauth.id = idauth.username
                        break
                
            amods.authors.append(modsauth)

        # journal info
        amods.create_journal()
        amods.journal.title = self.journal_title
        amods.journal.publisher = self.publisher
        if self.volume:
            amods.journal.create_volume()
            amods.journal.volume.number = self.volume
        if self.issue:
            amods.journal.create_number()
            amods.journal.number.number = self.issue
        if self.first_page and self.last_page:
            amods.journal.create_pages()
            amods.journal.pages.start = self.first_page
            amods.journal.pages.end = self.last_page
        if self.publication_date:
            amods.publication_date = unicode(self.publication_date)
        
        if self.abstract:
            amods.create_abstract()
            # nlm abstract may can contain formatting; convert to
            # text-only for now
            amods.abstract.text = unicode(self.abstract)

        if self.doi:
            amods.create_final_version()
            amods.final_version.doi = 'doi:%s' % self.doi

        # funding groups
        for sponsor in self.sponsors:
            amods.funders.append(FundingGroup(name=sponsor))

        # - add corresponding author info and related footnotes
        # as author individual author notes
        if self.author_notes:
            for an in self.author_notes:
                for txt in an.notes:
                    amods.author_notes.append(AuthorNote(text=txt))

        # capture article keywords, when available
        for kw in self.keywords:
            amods.keywords.append(Keyword(topic=kw))

        # TODO: investigate ext-link (can we determine type? or map to 'other links')

        amods.resource_type = 'text'
        # all content should be article;
        # (could check article/@article-type attribute to confirm...)
        amods.genre = 'Article'
        # TODO: what is the "version" of harvested content? (preprint? postprint?)

        # license
        if self.license:
            amods.create_license()
            amods.license.link = self.license.link
            amods.license.text = self.license.text
        elif self.copyright and 'creative commons' in self.copyright.lower():
            amods.create_license()
            amods.license.text = self.copyright

        # copyright
        if self.copyright:
            amods.create_copyright()
            amods.copyright.text = self.copyright

        return amods


class ArticlePremis(premis.Premis):
    '''Extend :class:`eulxml.xmlmap.premis.Premis` to add convenience
    mappings to admin review event, review date, harvest event, harvest date,
    upload event, date uploaded.
    '''

    #review event fields
    review_event = xmlmap.NodeField('p:event[p:eventType="review"]', premis.Event)
    date_reviewed = xmlmap.StringField('p:event[p:eventType="review"]/p:eventDateTime')

    #harvest event fields
    harvest_event = xmlmap.NodeField('p:event[p:eventType="harvest"]', premis.Event)
    date_harvested = xmlmap.StringField('p:event[p:eventType="harvest"]/p:eventDateTime')

    #upload event fields
    upload_event = xmlmap.NodeField('p:event[p:eventType="upload"]', premis.Event)
    date_uploaded = xmlmap.StringField('p:event[p:eventType="upload"]/p:eventDateTime')

    #withdraw event fields
    withdraw_events = xmlmap.NodeListField('p:event[p:eventType="withdraw"]', premis.Event)
    last_withdraw = xmlmap.NodeField('p:event[p:eventType="withdraw"][last()]', premis.Event)

    #reinstate event fields
    reinstate_events = xmlmap.NodeListField('p:event[p:eventType="reinstate"]', premis.Event)
    last_reinstate = xmlmap.NodeField('p:event[p:eventType="reinstate"][last()]', premis.Event)

    #symplectic-elements event fields
    symp_ingest_event = xmlmap.NodeField('p:event[p:eventType="symplectic elements ingest"]', premis.Event)
    date_symp_ingest = xmlmap.StringField('p:event[p:eventType="symplectic elements ingest"]/p:eventDateTime')

    def init_object(self, id, id_type):
        if self.object is None:
            self.create_object()
            self.object.type = 'p:representation'  # needs to be in premis namespace
            self.object.id_type = id_type
            self.object.id = id

    def premis_event(self, user, type, detail):
        '''Perform the common logic when creating premeis events. A :class:`~KeyError` Exception will be raised
        if the type is not in the list of allowed types.

        :param user: the :class:`~django.contrib.auth.models.User`
            who is performing the action.

        :param type: the type of event. Currently the allowed values are:

            * review
            * harvest
            * upload
            * withdraw
            * reinstate

        :param detail: detail message for event`
        '''

        #TODO add to this list as types grow
        allowed_types = ['review', 'harvest', 'upload', 'withdraw',
                         'reinstate', 'symp_ingest']

        if type not in allowed_types:
            raise KeyError("%s is not an allowed type. The allowed types are %s" % (type, ", ".join(allowed_types)))

        event = premis.Event()
        event.id_type = 'local'
        event.id = '%s.ev%03d' % (self.object.id, len(self.events)+1)
        event.type = type
        event.date = datetime.now().isoformat()
        event.detail = detail
        event.agent_type = 'netid'
        event.agent_id = user.username
        self.events.append(event)

    def reviewed(self, reviewer):
        '''Add an event to indicate that this article has been
        reviewed. Wrapper for :meth:`~openemory.publication.models.ArticlePremis.premis_event`

        :param reviewer: the :class:`~django.contrib.auth.models.User`
            who reviewed the article
        '''

        detail = 'Reviewed by %s' % reviewer.get_profile().get_full_name()
        self.premis_event(reviewer, 'review',detail)

    def harvested(self, user, pmcid):
        '''Add an event to indicate that this article has been
        harvested. Wrapper for :meth:`~openemory.publication.models.ArticlePremis.premis_event`

        :param user: the :class:`~django.contrib.auth.models.User`
            who harvested the article

        :param pmcid: the pmcid of the article in PubMed Central
        '''

        #TODO pmcid will have to change to something more general when more external systems are added

        detail = 'Harvested %s from PubMed Central by %s' % \
                              (pmcid, user.get_profile().get_full_name())
        self.premis_event(user, 'harvest', detail)

    def symp_ingest(self, user, id):
        '''Add an event to indicate that this article has been
        ingested from Symplectic-Elements. Wrapper for :meth:`~openemory.publication.models.ArticlePremis.premis_event`

        :param id: the id of the article in Symplectic-Elements
        '''


        # no log'd in user available so use OE Bot
        detail = 'Ingested %s from Symplectic-Elements by %s' % \
                              (id, user.get_profile().get_full_name())
        self.premis_event(user, 'symp_ingest', detail)

    def uploaded(self, user, legal_statement=None):
        '''Add an event to indicate that this article has been
        uploaded. Wrapper for :meth:`~openemory.publication.models.ArticlePremis.premis_event`

        :param user: the :class:`~django.contrib.auth.models.User`
            who uploaded the file
        :param legal_statement: string representing form of agreement
            indicated by user: 'AUTHOR' for agreement to author's Assent to
            Deposit; 'MEDIATED' for agreement to admin Mediated Deposit
            statement. This value should never be left as the default None:
            This will generate a statement that the item was uploaded
            without the user agreeing to a rights statement.
        '''

        # LEGAL NOTE: We expect legal_statement will always be set to one of
        # the expected values. We're leaving an explicit check here to make
        # the code a little more resistant against future change, since this
        # addition is intended to represent the user's explicit agreement to
        # certain legal statements and will be recorded in long-term
        # storage.
        if legal_statement == 'AUTHOR':
            detail = 'Uploaded by %s upon assent to deposit' % \
                    (user.get_profile().get_full_name(),)
        elif legal_statement == 'MEDIATED':
            detail = 'Mediated Deposit with Assist Authorization or CC or PD by %s' % \
                    (user.get_profile().get_full_name(),)
        else:
            detail = 'Uploaded by %s without confirmed assent to deposit' % \
                    (user.get_profile().get_full_name(),)
        detail += ' under OpenEmory v%s' % (openemory.__version__,)
            
        self.premis_event(user, 'upload', detail)

    def withdrawn(self, user, reason):
        '''Add an event to indicate that this article has been withdrawn
        from the public-facing collection by a site administrator.

        :param user: the :class:`~django.contrib.auth.models.User` who
            withdrew the article
        :param reason: user-entered string explaining the reason for
            withdrawal, to be included in the event detail
        '''
        detail = 'Withdrawn by %s: %s' % \
                (user.get_profile().get_full_name(), reason)
        self.premis_event(user, 'withdraw', detail)

    def reinstated(self, user, reason=None):
        '''Add an event to indicate that this article has been reinstated
        to the public-facing collection by a site administrator (after a
        past withdrawal).

        :param user: the :class:`~django.contrib.auth.models.User` who
            reinstated the article
        :param reason: optional user-entered string explaining the reason
            for reinstatement, to be included in the event detail
        '''
        if reason is None:
            reason = 'No reason given.'
        detail = 'Reinstated (from withdrawal) by %s: %s' % \
                (user.get_profile().get_full_name(), reason)
        self.premis_event(user, 'reinstate', detail)


def _make_parsed_author(mods_author):
    '''Generate a solr parsed_author field from a MODS author. Currently
    that solr field has the format "netid:Published Name".
    '''
    netid = mods_author.id or ''
    return '%s:%s %s' % (netid, mods_author.given_name,
                         mods_author.family_name)

def year_quarter(month):
    '''
    Returns the quarter the year based on month param.
    For example month 2 would return 1, month 4 would return 2
    '''
    if month < 1 or month > 12:
        raise ValueError("Month must be between 1 and 12")
    return (month-1)/3+1


class Article(DigitalObject):
    '''Subclass of :class:`~openemory.common.fedora.DigitalObject` to
    represent Scholarly Articles.
    
    Following `Hydra content model`_ conventions where appropriate;
    similar to the generic simple Hydra content model
    `genericContent`_.

    .. _Hydra content model: https://wiki.duraspace.org/display/hydra/Hydra+objects%2C+content+models+%28cModels%29+and+disseminators
    .. _genericContent: https://wiki.duraspace.org/display/hydra/Hydra+objects%2C+content+models+%28cModels%29+and+disseminators#Hydraobjects%2Ccontentmodels%28cModels%29anddisseminators-genericContent
    '''
    ARTICLE_CONTENT_MODEL = 'info:fedora/emory-control:PublishedArticle-1.0'
    CONTENT_MODELS = [ ARTICLE_CONTENT_MODEL ]
    collection = Relation(relsext.isMemberOfCollection)
    oai_itemID = Relation(oai.itemID)

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


    provenance = XmlDatastream('provenanceMetadata',
                                       'Provenance metadata', ArticlePremis, defaults={
        'versionable': False 
        })
    '''Optional ``provenanceMetadata`` datastream for PREMIS Event
    metadata; datastream XML content will be an instance of
    :class:`ArticlePremis`.'''
    # NOTE: datastream naming based on Hydra cnotent model documentation
    # https://wiki.duraspace.org/display/hydra/Hydra+objects%2C+content+models+%28cModels%29+and+disseminators
    # 	provenanceMetadata (XML, optional)- this datastream may
    # 	   contain, for instance, PREMIS premisEvents.

    authorAgreement = FileDatastream('authorAgreement', 'Author agreement', defaults={
        'mimetype': 'application/pdf',
        'versionable': True
        })
    '''Optional ``authorAgreement`` datastream stores the authors' agreement
    (if available) with the publisher.'''
    # NOTE: authorAgreement isn't in the Hydra content model. Neither is
    # anything like it. So we just follow their naming style here.

    sympAtom = XmlDatastream('SYMPLECTIC-ATOM', 'SYMPLECTIC-ATOM',
        SympAtom, defaults={
            'versionable': True,
        })
    '''Descriptive Metadata datastream, as :class:`ArticleMods`'''



    def get_absolute_url(self):
        ark_uri = self.descMetadata.content.ark_uri
        return ark_uri or reverse('publication:view',  kwargs={'pid': self.pid})

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


    def _mods_to_dc(self):
        '''
        Maps valies from MOS to DC for use with OAI
        '''
        if self.descMetadata and self.dc:
            mods = self.descMetadata.content
            dc = self.dc.content

            # title and subtitle
            if mods.title_info:
                title =  mods.title_info.title
                if mods.title_info.subtitle:
                    title += ': ' + mods.title_info.subtitle
                dc.title_list =  [title]


            # author full names
            dc.contributor_list = ['%s %s' % (author.given_name, author.family_name)
                                   for author in mods.authors]
            # types and version
            types = []
            types.append("text")
            if mods.version:
                types.append("%s: %s" % (mods.version, 'article'))
            else:
                types.append('article')
            dc.type_list =  types

            # language
            dc.language = mods.language

            # mime type
            if mods.physical_description:
                dc.format = mods.physical_description.media_type

            # abstract
            if mods.abstract:
                dc.description = mods.abstract.text

            # subject and keywords
            subjects = mods.subjects
            keywords = mods.keywords
            dc.subject_list = [s.topic for s in subjects]
            dc.subject_list.extend([k.topic for k in keywords])


#            relations = []
#
#            # perm link
#            relations.append(mods.ark_uri)
#            dc.relation_list = relations

            # publisher info
            # Title, Volume, Issue, Publication Date and Pagination
            if mods.journal:
                if mods.journal:
                    volume = mods.journal.volume.number if mods.journal.volume else ''
                    issue = mods.journal.number.number if mods.journal.number else ''
                    if mods.journal.pages:
                        p_start = mods.journal.pages.start
                        p_end = mods.journal.pages.end
                    else:
                        p_start = ''
                        p_end = ''

                    pub_info = '%s Volume %s Issue %s Date %s Pages %s-%s' % \
                           (mods.journal.title,
                           volume,
                           issue,
                           mods.publication_date,
                           p_start, p_end)
                    dc.source = pub_info


    def save(self, *args, **kwargs):
        '''Extend default :meth:`eulfedora.models.DigitalObject.save`
        to update a few fields before saving to Fedora.

          * set object owners based on ids from authors set in
            :attr:`descMetadata` content; if this would result in no owners,
            the previous value is left as is.
        '''
        # update owners based on identified emory authors in the metadata
        new_owners = self.OWNER_ID_SEPARATOR.join(auth.id for auth
                                                   in self.descMetadata.content.authors
                                                   if auth.id)
        # only update if there are new owners; don't clear out an existing owner
        # without setting a new owner
        if new_owners:
            self.owner = new_owners

        # Remove control character \r  from abstract
        if self.descMetadata.content.abstract is not None and self.descMetadata.content.abstract.text:
                self.descMetadata.content.abstract.text = self.descMetadata.content.abstract.text.replace('\r', '')

        # map MODS values into DC
        self._mods_to_dc()

        return super(Article, self).save(*args, **kwargs)

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
        :meth:`openemory.common.fedora.DigitalObject.index_data` method to
        include fields needed for search and display of Article
        objects.'''
        data = super(Article, self).index_data()

        data['id'] = 'pid: %s' % self.pid
        data['withdrawn'] = self.is_withdrawn
        # TODO: 
        data['record_type'] = 'publication_article' # ???
        # following django convention: app_label, model

        # embargo_end date
        if self.descMetadata.content.embargo_end:
            data['embargo_end'] = self.descMetadata.content.embargo_end


        # add full document text from pdf if available and not embargoed
        if self.pdf.exists and not self.is_embargoed:
            try:
                data['fulltext'] = pdf_to_text(self.pdf.content)
            except Exception as e:
                # errors if datastream cannot be read as a pdf
                # (should be less of an issue after we add format validation)
                logger.error('Failed to read %s pdf datstream content for indexing: %s' \
                             %  (self.pid, e))


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
                    data['journal_title_sorting'] = '%s|%s' % \
                            (mods.journal.title.lower(), mods.journal.title)
                if mods.journal.publisher:
                    data['journal_publisher'] = mods.journal.publisher
            if mods.abstract:
                data['abstract'] = mods.abstract.text
            if mods.keywords:
                data['keyword'] = [kw.topic for kw in mods.keywords]
            if mods.subjects:
                data['researchfield_id'] = [rf.id for rf in mods.subjects]
                data['researchfield'] = [rf.topic for rf in mods.subjects]
                data['researchfield_sorting'] = ['%s|%s' % (rf.topic.lower(), rf.topic)
                                                 for rf in mods.subjects]
            if mods.author_notes:
                data['author_notes'] = [a.text for a in mods.author_notes]
            if mods.publication_date is not None:
                # index year separately, since all dates should have at least year
                data['pubyear'] = mods.publication_date[:4]
                data['pubdate'] = mods.publication_date
            if mods.language is not None:
                data['language'] = [mods.language]
            if mods.authors:
                mods_authors = ['%s, %s' % (a.family_name, a.given_name)
                                for a in mods.authors]
                sorting_authors = ['%s|%s' % (a.lower(), a)
                                   for a in mods_authors]
                # *replace* any dc:authors to ensure
                # we don't duplicate names in variant forms
                # check for dc authors and add to them if set
                data['creator'] = mods_authors

                data['author_affiliation'] = list(set(a.affiliation
                                                      for a in mods.authors
                                                      if a.affiliation))
                data['affiliations'] = self.affiliations
                data['parsed_author'] = [_make_parsed_author(a)
                                         for a in mods.authors]
                data['creator_sorting'] = sorting_authors
                data['division_dept_id'] = self.division_dept_id
                data['department_shortname'] = self.department_shortname

        # get contentMetadata (NLM XML) bits
        if self.contentMetadata.exists:
            # some contentMetadata datastreams can't be loaded - *probably* bogus dev/test data
            # - but don't blow up if contentMetadata exists but can't be loaded
            try:
                nxml = self.contentMetadata.content
                if 'fulltext' not in data and nxml.body:
                    data['fulltext'] = unicode(nxml.body)
                if nxml.abstract and \
                       'abstract' not in data:	# let MODS abstract take precedence
                    data['abstract'] = unicode(nxml.abstract)
            except Exception as e:
                logger.error('Failed to load %s contentMetadata as xml for indexing: %s' \
                             %  (self.pid, e))

        # if provenanceMetadata datastream exists, check for review date
        if self.provenance.exists:
            if self.provenance.content.date_reviewed:
                data['review_date'] = self.provenance.content.date_reviewed

        # index the pubmed central id, if we have one
        pmcid = self.pmcid
        if pmcid:
            data['pmcid'] = pmcid
            if pmcid in data['identifier']:	# don't double-index PMC id
                data['identifier'].remove(pmcid)

        return data

    @property
    def author_netids(self):
        if not self.descMetadata.exists:
            return []
        mods = self.descMetadata.content
        return [a.id for a in mods.authors if a.id]

    @property
    def author_esd(self):
        result = []
        for netid in self.author_netids:
            try:
                user = User.objects.get(username=netid)
                profile = user.get_profile()
                esd = profile.esd_data()
                result.append(esd)
            except ObjectDoesNotExist:
                pass
        return result

    @property
    def affiliations(self):
        return [str(aff)
                for esd in self.author_esd
                for aff in esd.affiliations]

    @property
    def department_name(self):
        return [esd.department_name for esd in self.author_esd]

    @property
    def department_shortname(self):
        return [esd.department_shortname for esd in self.author_esd]

    @property
    def division_dept_id(self):
        return [esd.division_dept_id for esd in self.author_esd]

    # FIXME: this is a pretty ugly way to just call a method on EsdPerson.
    # it's so indirect because we want to avoid depending directly on
    # accounts (where EsdPerson lives) because accounts already depends on
    # publication. clearly, though, a better dependency structure is needed
    # here.
    @staticmethod
    def split_department(division_dept_id):
        app_label, model_name = settings.AUTH_PROFILE_MODULE.split('.')
        profile_model = models.get_model(app_label, model_name)
        esd_model = profile_model.esd_model()
        return esd_model.split_department(division_dept_id)

    @property
    def pmcid(self):
        for id in self.dc.content.identifier_list:
            if id.startswith('PMC') and not id.endswith("None"):
                return id[3:]
    
    @property
    def embargo_end(self):
        '''Return :attr:`ArticleMods.embargo_end` '''
        if self.descMetadata.content.embargo_end:
          return self.descMetadata.content.embargo_end
        return None
    
    @property
    def embargo_end_date(self):
        '''Access :attr:`ArticleMods.embargo_end` on the local
        :attr:`descMetadata` datastream as a :class:`datetime.date`
        instance.'''

        if self.descMetadata.content.embargo_end:
            
            if self.descMetadata.content.embargo =='':
              return self.descMetadata.content._embargo
            
            if slugify(self.descMetadata.content.embargo_end) == slugify(NO_LIMIT["value"]):
                try:
                  y, m, d = self.descMetadata.content.publication_date.split('-')
                  return date(int(y), int(m), int(d))+relativedelta(months=+48)
                except:
                  return NO_LIMIT["display"]
                
            if slugify(self.descMetadata.content.embargo_end) == slugify(UNKNOWN_LIMIT["value"]):
                try:
                  y, m, d = self.descMetadata.content.publication_date.split('-')
                  return date(int(y), int(m), int(d))+relativedelta(months=+6)
                except:
                  return UNKNOWN_LIMIT["display"]
                
            y, m, d = self.descMetadata.content.embargo_end.split('-')
            return date(int(y), int(m), int(d))
            
        return None

    @property
    def is_embargoed(self):
        '''boolean indicator that this article is currently embargoed
        (i.e., there is an embargo end date set and that date is not
        in the past).'''
        
        if slugify(self.embargo_end_date) == slugify(NO_LIMIT["display"]) or \
           slugify(self.embargo_end_date) == slugify(UNKNOWN_LIMIT["display"]):
            return True
            
        return self.descMetadata.content.embargo_end and  \
               date.today() <= self.embargo_end_date

    @property
    def is_published(self):
        '''boolean indicator that this article is currently published
        (currently defined as object by object state being **active**).'''
        return self.state == 'A'

    @property
    def is_withdrawn(self):
        '''boolean indicator that this article is currently withdrawn from
        the public-facing website.'''

        # if the article is active, it's not withdrawn.
        if self.state != 'I':
            return False

        # if there are no withdrawal events, it's not withdrawn.
        provenance = self.provenance.content
        if not provenance.last_withdraw:
            return False
        # if there are withdrawals and no reinstates, it *is* withdrawn
        if not provenance.last_reinstate:
            return True

        # if there are both, then most recent one wins.
        return provenance.last_withdraw.date >= provenance.last_reinstate.date

    def statistics(self, year=None, quarter=None):
        '''Get the :class:`ArticleStatistics` for this object on the given
        year and / or quarter. If no year is specified, use the current year.
        If no quarter is specified, use the current quarter.
        Returns None if this article does not yet have a PID.
        '''
        if year is None:
            year = date.today().year
        if quarter is None:
            quarter = year_quarter(date.today().month) #get the quarter 1, 2, 3, 4

        if not isinstance(self.pid, basestring):
            return None

        stats, created = ArticleStatistics.objects.get_or_create(pid=self.pid, year=year, quarter=quarter)
        return stats

    def statistics_queryset(self):
        '''Get a :class:`~django.db.models.query.QuerySet` for all this
        article's :class:`ArticleStatistics`. Returns None if this article
        does not yet have a PID.
        '''
        if not isinstance(self.pid, basestring):
            return None
        return ArticleStatistics.objects.filter(pid=self.pid)

    def aggregate_statistics(self):
        '''Get statistics for this article, aggregated across all available
        :class:`ArticleStatistics` objects.

        :returns: a dictionary with ``num_views`` and ``num_downloads``
                  members
        '''
        qs = self.statistics_queryset()
        if qs:
            return qs.aggregate(num_views=models.Sum('num_views'),
                                num_downloads=models.Sum('num_downloads'))

    ### PDF generation methods for Article cover page ###

                
    def pdf_cover(self):
        '''Generate a PDF cover page based on the MODS descriptive
        metadata associated with this article (:attr:`descMetadata`),
        using :mod:`xhtml2pdf`.

        :returns: a :class:`cStringIO.StringIO` with PDF content
        '''

        start = time.time()
        tpl = get_template('publication/coverpage.html')
        # full URLs are required for external links in pisa PDF documents
        base_url = Site.objects.get_current().domain  
        if not base_url.startswith('http'):
            base_url = 'http://' + base_url
            
        ctx = Context({
            'article': self,
            'BASE_URL': base_url,
            })
        html = tpl.render(ctx)
        result = StringIO()
        # NOTE: to include images & css, pisa requires a filename path.
        # Setting path relative to sitemedia directory so STATIC_URL paths will (generally) work.
        pdf = pisa.pisaDocument(StringIO(html.encode('UTF-8')), result,
                                path=os.path.join(settings.BASE_DIR, '..', 'sitemedia', 'pdf.html'))
        logger.debug('Generated cover page for %s in %f sec ' % \
                     (self.pid, time.time() - start))
        if not pdf.err:
            return result

    def pdf_with_cover(self):
        '''Return the PDF associated with this article (the contents
        of the :attr:`pdf` datastream) with a custom cover page
        (generated by :meth:`pdf_cover`).

        .. Note::
          This method currently does **not** trap for errors such as \
          :class:`pyPdf.util.PdfReadError` or \
          :class:`eulfedora.util.RequestFailed` (e.g., if the \
          datastream does not exist or cannot be accessed, or the \
          datastream exists but the PDF is unreadable with \
          :mod:`pyPdf`). 

        :returns: :class:`cStringIO.StringIO` instance with the \
        merged pdf content
        '''
        # NOTE: pyPdf PdfFileWrite currently does not supply a
        # mechanism to set document info / metadata (title, author, etc.)
        # Cover page PDF is being generated with embedded metadata.
        # When/if it becomes possible, use coverdoc info to set the
        # docinfo for the merged pdf.
        
        coverdoc = self.pdf_cover() 
        start = time.time()
        pdfstream = StringIO()  # io buffer for pdf datastream content
        try:
            # create a new pdf file writer to merge cover & pdf into
            doc = PdfFileWriter()
            # load and add cover page first
            cover = PdfFileReader(coverdoc)
            doc.addPage(cover.pages[0])
            # load pdf datastream contents into a file-like object
            for ch in self.pdf.get_chunked_content():
                pdfstream.write(ch)
            # load pdf content into a pdf reader and add all pages
            content = PdfFileReader(pdfstream)
            for p in range(content.numPages):
                doc.addPage(content.pages[p])

            # write the resulting pdf to a buffer and return it
            result = StringIO()
            doc.write(result)
            # seek to beginning for re-use (e.g., django httpresponse content)
            result.seek(0)
            logger.debug('Added cover page to PDF for %s in %f sec ' % \
                         (self.pid, time.time() - start))
            return result
        finally:
            coverdoc.close()  # delete xsl-fo
            pdfstream.close() # close iostream for pdf content



    def _prep_dc_for_oai(self):
        '''Removes namespaces that cause OAI a problem'''

        if 'xsi' in self.dc.content.node.nsmap:
            # Remove SchemaLocation Attribute
            del self.dc.content.node.attrib['{%s}%s' % (self.dc.content.node.nsmap['xsi'], 'schemaLocation')]
   
            # Remove namespace declaration
            nsmap = self.dc.content.node.nsmap
            del nsmap['xsi']
            new_node = etree.Element(self.dc.content.node.tag, nsmap=nsmap)
            new_node[:] = self.dc.content.node[:]
            self.dc.content.node = new_node

    def as_symp(self, source='manual', source_id=None):
        """
        Takes an optional source param that will set the source in the :class:`SympRelation` objects.
        source_id param that will set the source-id in the :class:`SympRelation` objects.
        Returns a :class:`OESympImportArticle` object
        and a list of :class:`SympRelation` objects
        for use with Symplectic-Elements
        """
        # build article xml
        relations = []
        mods = self.descMetadata.content
        symp_pub = OESympImportArticle()
        if mods.title_info:
            title = mods.title_info.title
            if mods.title_info.subtitle:
                title += ': ' + mods.title_info.subtitle
            symp_pub.title = title
        if mods.abstract:
            symp_pub.abstract = mods.abstract.text
        if mods.final_version and mods.final_version.doi:
            symp_pub.doi = mods.final_version.doi.lstrip("doi:")
        if mods.journal:
            symp_pub.volume = mods.journal.volume.number if mods.journal.volume and mods.journal.volume.number  else None
            symp_pub.issue = mods.journal.number.number if mods.journal.number and mods.journal.number.number else None
            symp_pub.journal = mods.journal.title if mods.journal.title else None
            symp_pub.publisher = mods.journal.publisher if mods.journal.publisher else None
        if mods.publication_date:
            day, month, year = None, None, None
            date_info = mods.publication_date.split('-')
            if len(date_info) >= 1:
                year = str(date_info[0]).lstrip('0')
            if len(date_info) >= 2:
                month = str(date_info[1]).lstrip('0')
            if len(date_info) >= 3:
                day = str(date_info[2]).lstrip('0')

            # order day, month, year is required
            pub_date = SympDate()
            pub_date.day = day
            pub_date.month = month
            pub_date.year = year
            if not pub_date.is_empty():
                symp_pub.publication_date = pub_date

        if self.pmcid:
            symp_pub.pmcid = "PMC%s" % self.pmcid

        symp_pub.language = mods.language if mods.languages else None
        symp_pub.keywords = [k.topic for k in mods.keywords]
        symp_pub.notes = ' ; '.join([n.text for n in mods.author_notes if n.text])

        pub_id = source_id if source_id else self.pid
        for a in mods.authors:
            fam = a.family_name if a.family_name else ''
            given = a.given_name if a.given_name else ''
            symp_pub.authors.append(SympPerson(last_name=fam, initials="%s%s" % (given[0].upper(), fam[0].upper())))
            if a.id:
                rel = SympRelation()
                rel.from_object="publication(source-%s,pid-%s)" % (source, pub_id)
                rel.to_object="user(username-%s)" % a.id
                rel.type_name=SympRelation.PUB_AUTHOR
                relations.append(rel)

        return (symp_pub, relations)

    def from_symp(self):
        '''Modifies the current object and datastreams to be a :class:`Article`
        '''
        symp = self.sympAtom.content
        mods = self.descMetadata.content

        # object attributes
        self.label = symp.title
        self.descMetadata.label='descMetadata(MODS)'

        ark_uri = '%sark:/25593/%s' % (settings.PIDMAN_HOST, self.pid.split(':')[1])

        #RELS-EXT attributes
        self.add_relationship(relsextns.hasModel, self.ARTICLE_CONTENT_MODEL)

        # DS mapping
        mods.resource_type= 'text'
        mods.genre = 'Article'
        mods.ark_uri = ark_uri
        mods.ark = 'ark:/25593/%s' % (self.pid.split(':')[1])
        mods.title=symp.title
        mods.create_journal()
        mods.journal.create_volume()
        mods.journal.create_number()
        mods.journal.volume.number = symp.volume
        mods.journal.number.number = symp.issue
        if symp.pages:
            mods.journal.create_pages()
            mods.journal.pages.start = symp.pages.begin_page
            mods.journal.pages.end = symp.pages.end_page if symp.pages.end_page else symp.pages.begin_page

        mods.journal.publisher = symp.publisher
        mods.journal.title = symp.journal
        mods.create_final_version()
        mods.final_version.doi = 'doi:%s' % symp.doi
        mods.final_version.url = 'http://dx.doi.org/%s' % symp.doi
        mods.create_abstract()
        mods.create_abstract() 
        mods.abstract.text = symp.abstract
        mods.language_code = symp.language[0]
        mods.language = symp.language[1]
        
        if symp.pubdate:
            mods.publication_date = symp.pubdate.date_str
            
        mods.embargo = symp.embargo
        
        mods.calculate_embargo_end()

        mods.keywords = []
        for kw in symp.keywords:
            mods.keywords.append(Keyword(topic=kw))

        mods.authors = []
        for u in symp.users:
            a = AuthorName(id=u.username.lower(), affiliation='Emory University', given_name=u.first_name, family_name=u.last_name)
            mods.authors.append(a)

        mods.create_admin_note()
        mods.admin_note.text = symp.comment

class ArticleRecord(models.Model):
    # place-holder class for custom permissions
    class Meta:
        permissions = (
            # add, change, delete are avilable by default
            ('review_article', 'Can review articles'),
            ('view_embargoed', 'Can view embargoed content'),
            ('view_admin_metadata', 'Can view admin metadata content'),
        )


class ArticleStatistics(models.Model):
    '''Aggregated access statistics for a single :class:`Article`.
    Subdivided by year and quarter to allow quarterly reporting.
    '''

    # stats are collected (currently) for a particular pid in a particular
    # year and quarter. if we ever calculate them, e.g., per-month, then that'll go here
    # too (and below in unique_together)
    pid = models.CharField(max_length=50)
    year = models.IntegerField()
    quarter = models.IntegerField() #1, 2, 3, 4

    # the things we store for this pid/year/quarter
    num_views = models.IntegerField(default=0,
            help_text='metadata view page loads')
    num_downloads = models.IntegerField(default=0, 
            help_text='article PDF downloads')

    class Meta:
        unique_together = (('pid', 'year', 'quarter'),)
        verbose_name_plural = 'Article Statistics'


### simple XmlObject mapping to access LOC codelist document for MARC
### language names & codes

CODELIST_NS = "info:lc/xmlns/codelist-v1"

class CodeListBase(xmlmap.XmlObject):
    # base class for CodeList xml objects
    ROOT_NS = CODELIST_NS
    ROOT_NAMESPACES = {'c': CODELIST_NS }

class CodeListLanguage(CodeListBase):
    name = xmlmap.StringField('c:name')
    code = xmlmap.StringField('c:code')
    uri = xmlmap.StringField('c:uri')

class CodeList(CodeListBase):
    id = xmlmap.StringField('c:codelistId')
    title = xmlmap.StringField('c:title')
    author = xmlmap.StringField('c:author')
    uri = xmlmap.StringField('c:uri')
    languages = xmlmap.NodeListField('c:languages/c:language',
                                     CodeListLanguage)

def marc_language_codelist():
    '''Initialize and return :class:`CodeList` instance from the MARC
    languages Code List.
    '''
    marc_languages_xml = 'http://www.loc.gov/standards/codelists/languages.xml'
    # NOTE: for now, rely on HTTP caching as we do for XML Schemas
    logger.info('Loading MARC language code list from %s' % marc_languages_xml)
    return xmlmap.load_xmlobject_from_file(marc_languages_xml,
                                           xmlclass=CodeList)


# SKOS namespace for UMI/ProQuest research fields

# classes & properties copied from http://www.w3.org/2009/08/skos-reference/skos.html
skos_terms = [
    'Collection',
    'Concept',
    'ConceptSchema',
    'OrderedCollection',
    'altLabel',
    'broadMatch',
    'broder',
    'broaderTransitive',
    'changeNote',
    'closeMatch',
    'definition',
    'editorialNote',
    'exactMatch',
    'example',
    'hasTopConcept',
    'hiddenLabel',
    'historyNote',
    'inSchema',
    'mappingRelation',
    'member',
    'memberlist',
    'narrowMatch',
    'narrow',
    'notation',
    'note',
    'prefLabel',
    'related',
    'relatedMatch',
    'scopeNote',
    'semanticRelation',
    'topConceptOf'
]


SKOS = ClosedNamespace('http://www.w3.org/2004/02/skos/core#',
                          skos_terms)

class ResearchFields(object):
    '''Wrapper-class for access to UMI/ProQuest research fields (also
    known as Subject Categories). 
    '''
    
    # for now, use local copy; may move to http://pid.emory.edu/ns/ or similar
    source = os.path.join(settings.BASE_DIR, 'publication',
                                        'fixtures', 'umi-researchfields.xml')

    def __init__(self):
        with open(self.source) as rff:
            self.graph = parse_rdf(rff.read(), self.source)
            
        # loop through all collections to get hierarchy information
        # and find the top-level collection
        self.toplevel = None
        self.hierarchy = defaultdict(list)
        for s in self.graph.subjects(predicate=RDF.type, object=SKOS.Collection):
            parents = list(self.graph.subjects(predicate=SKOS.member, object=s))
            if not parents:
                self.toplevel = s
            else:
                self.hierarchy[parents[0]].append(s)
        # error if toplevel is not found ?

    def get_label(self, id):
        if not isinstance(id, URIRef):
            id = URIRef(id)
        return str(self.graph.label(id))


    def as_field_choices(self):
        '''Generate and a list of choices, based on the SKOS
        collection hierarchy, that can be used with a
        :class:`django.forms.ChoiceField`.
        '''
        return self._flatten_choices(self._get_choices())

    def _flatten_choices(self, choices, prefix=''):
        '''Sort and flatten a nested list of choices (as returned by
        :meth:`_get_choices`) into a two-level format that can be used
        as the choices for a :class:`django.forms.ChoiceField`.

        Groups that *only* contain sublists will be added to the
        flattened list as an empty group; nested group labels will
        have a prefix added to indicate the hierarchy.

        :param choices: list of [id,val] entries OR a list of [label,
             [choices]], where sublists may recurse :param prefix:
             optional prefix; add to subgroup labels to indicate
             hierarchy in the flattened list (should only be used when
             recursing to flatten a sublist)

        :returns: a list with at most two-levels of nesting, for use
             as choices value for a :class:`django.forms.ChoiceField`.
        '''
        
        flat_choices = []

        for choice in sorted(choices):
            if isinstance(choice[1], list):
                if all(isinstance(val, list) for label,val in choice[1]):
                    # this group only has sublists; add empty group marker
                    flat_choices.append(['%s%s' % (prefix, choice[0]), []])
                    # prefix sublabels with '-' and recurse
                    flattened = self._flatten_choices(choice[1], '%s-' % prefix)
                    if flattened:
                        flat_choices.extend(flattened)

                elif all(isinstance(val, basestring) for label,val, in choice[1]):
                    # this group only has values, no list - add as-is 
                    flat_choices.append(['%s%s' % (prefix, choice[0]), choice[1]])
                    
                else:
                    # group has a mixture of subchoices and sublists
                    # gather all the values and add them
                    subchoices = []
                    for label,val in sorted(choice[1]):
                        if isinstance(val, basestring):
                            subchoices.append([label, val])
                    flat_choices.append(['%s%s' % (prefix, choice[0]), subchoices])

                    # add each of the sublists with a '-' prefix
                    for sublist in choice[1]:
                        if isinstance(sublist[1], list):
                            flat_choices.append(['%s-%s' % (prefix, sublist[0]), sorted(sublist[1])])

        return flat_choices

    def _get_choices(self, id=None):
        '''Convert the SKOS collection hierarchy into nested
        lists. The nested list structure generated roughly follows the
        format needed for specifing choice options to a
        :class:`django.forms.ChoiceField`, except that the return
        result nests as deeply as the SKOS hierarchy goes
        (:class:`~django.forms.ChoiceField` only supports one level of
        nesting).

        :param id: optional id of the collection to get choices for;
           if none is specified, the top-level collection id will be
           used.
        '''
        
        if id is None:
            return [self._get_choices(m) for m in self.hierarchy[self.toplevel]]
        # check if item has members
        if self.hierarchy[id]:
            # find all the members that don't themselves have children
            member_list = [self._get_choices(m) for m in self.hierarchy[id]]
            
            return [str(self.graph.label(id)), member_list]
        else:
            return [str(id), str(self.graph.label(id))]


    def as_category_completion(self):
        '''Flatten the SKOS hierarchy into a list of dictionaries that
        can be used as the basis for a category-based jQueryUI
        autocomplete (see http://jqueryui.com/demos/autocomplete/#categories ).
        '''
        return self._get_category_data()

    def _get_category_data(self, id=None, category=''):
        '''Recursive function to generate a category list for
        :meth:`as_category_completion`.

        :param id: id for the portion of the hierarchy to handle;
            if not specified, assumes top-level
        :param category: category prefix to be applied to items at the
            current level of the hierarchy.
        '''
        category_list = []
        if id is None:
            # recurse from top-level of hierarchy with no label
            for m in self.hierarchy[self.toplevel]:
                category_list.extend(self._get_category_data(m))
            return category_list
        
        # item with members
        if self.hierarchy[id]:
            # add current heading to subcategory
            if category:
                subcategory = '%s: %s' % (category, self.graph.label(id))
            else:
                subcategory = unicode(self.graph.label(id))
            # recurse with subcategory label
            for m in self.hierarchy[id]:
                category_list.extend(self._get_category_data(m, subcategory))
            return category_list

        # single item
        else:
            itemdata = {'id': "id%s" % str(id).strip('#'),
                        'label': str(self.graph.label(id))}
            if category:
                itemdata['category'] = category
            return [itemdata]

class FeaturedArticle(models.Model):
    '''
    List of pid associated with article that are marked as Featured. One of these is
    selected at random and displayed on the homepage in the
    Slider.
    '''
    pid = models.CharField(max_length=60, unique=True)

    def __unicode__(self):
        solr = solr_interface()
        title = solr.query(pid=self.pid).field_limit('title').execute()[0]['title']
        return title

class License(models.Model):
    short_name = models.CharField(max_length=30, unique=True)
    title  = models.CharField(max_length=100, unique=True)
    version = models.CharField(max_length=5)
    url = models.URLField(unique=True)

    def __unicode__(self):
        return "(%s) %s" % (self.short_name, self.title)

    @property
    def label(self):
        return self.__unicode__()


# Symplectic Export Models
class SympBase(xmlmap.XmlObject):
    '''
    Base class for Symplectic-Elements xml
    '''

    api_ns = 'http://www.symplectic.co.uk/publications/api'
    atom_ns = 'http://www.w3.org/2005/Atom'
    ROOT_NAMESPACES = {'api': api_ns, 'atom': atom_ns}
    ROOT_NS = api_ns
    XSD_SCHEMA = settings.BASE_DIR + '/publication/symp-api46.xsd'


class SympEntry(SympBase):
    '''Minimal wrapper for Symplectic-Elements article'''

    ROOT_NS = 'http://www.w3.org/2005/Atom'
    ROOT_NAME = 'entry'


    source = xmlmap.StringField("(api:object/api:records/api:record/@source-name)[1]")
    '''first symplectic source of publication'''

    source_id = xmlmap.StringField("(api:object/api:records/api:record/@id-at-source)[1]")
    '''id in first symplectic source'''

    title = xmlmap.StringField('atom:title')
    '''title of article'''


class SympOEImportArticle(SympBase):
    '''Minimal wrapper for Symplectic-Elements articles being imported into OE'''

    ROOT_NS = 'http://www.w3.org/2005/Atom'
    ROOT_NAME = 'feed'

    entries = xmlmap.NodeListField('atom:entry', SympEntry)
    '''List of Articles'''

    #TODO Remaining feilds that needto be found
    # Authors (FN, LN, AFF, netids for owners)
    # Article Version


# Import into Symplectic-Elements

class SympPerson(SympBase):
    '''Person Info'''

    ROOT_NAME = 'person'

    last_name = xmlmap.StringField('api:last-name')
    '''Last name of person'''

    initials = xmlmap.StringField('api:initials')
    '''Initials of person'''

class SympDate(SympBase):
    '''Date Info'''

    ROOT_NAME = 'date'

    day = xmlmap.StringField('api:day')
    '''Day portion of date'''

    month = xmlmap.StringField('api:month')
    '''Month portion of date'''

    year = xmlmap.StringField('api:year')
    '''Year portion of date'''



class SympWarning(SympBase):
    '''Warning returned from publication creation'''

    ROOT_NAME = 'warning'

    message = xmlmap.StringField("text()")
    '''Warning message'''


class OESympImportArticle(SympBase):
    '''Minimal wrapper for Symplectic-Elements articles being imported from OE'''

    ROOT_NAME = 'import-record'

    types = xmlmap.StringListField("api:native/api:field[@name='types']/api:items/api:item")
    '''Subtype of publication (defaults to Article)'''

    type_id = xmlmap.StringField("@type-id")
    '''Type Id of Article (defaults to 5)'''

    title = xmlmap.StringField("api:native/api:field[@name='title']/api:text")
    '''Title of Article'''

    language = xmlmap.StringField("api:native/api:field[@name='language']/api:text")
    '''Language of Article'''

    abstract = xmlmap.StringField("api:native/api:field[@name='abstract']/api:text")
    '''Abstract of Article'''

    volume = xmlmap.StringField("api:native/api:field[@name='volume']/api:text")
    '''Volume of Article'''

    issue = xmlmap.StringField("api:native/api:field[@name='issue']/api:text")
    '''Volume of Article'''

    publisher = xmlmap.StringField("api:native/api:field[@name='publisher']/api:text")
    '''Publisher of Article'''

    publisher = xmlmap.StringField("api:native/api:field[@name='publisher']/api:text")
    '''Publisher of Article'''

    publication_date = xmlmap.NodeField("api:native/api:field[@name='publication-date']/api:date", SympDate)
    '''Date of publication of Article'''

    authors = xmlmap.NodeListField("api:native/api:field[@name='authors']/api:people/api:person", SympPerson)
    '''Authors associated with Article'''

    doi = xmlmap.StringField("api:native/api:field[@name='doi']/api:text")
    '''DOI of Article'''

    keywords = xmlmap.StringListField("api:native/api:field[@name='keywords']/api:keywords/api:keyword")
    '''Keywords of Article'''

    journal = xmlmap.StringField("api:native/api:field[@name='journal']/api:text")
    '''Journal Name in which the Article appears'''

    notes = xmlmap.StringField("api:native/api:field[@name='notes']/api:text")
    '''Author Notes on the Article'''

    pmcid = xmlmap.StringField("api:native/api:field[@name='external-identifiers']/api:identifiers/api:identifier[@scheme='pmc']")
    '''PMCID Article appears'''


    warnings = xmlmap.NodeListField('//api:warning', SympWarning)
    '''Warning returned after publication creation'''

    entries = xmlmap.NodeListField('//atom:entry', SympEntry)
    '''entries returned from query'''


    def __init__(self, *args, **kwargs):
        super(OESympImportArticle, self).__init__(*args, **kwargs)

        self.type_id = 5

        self.types = ["Article"]

    def is_empty(self):
        """Returns True if all fields are empty, and no attributes
        other than **type_id** . False if any fields
        are not empty."""

        # ignore these fields when checking if a related item is empty
        ignore = ['type_id', 'types']  # type attributes

        for name in self._fields.iterkeys():
            if name in ignore:
                continue
            f = getattr(self, name)
            # if this is an XmlObject or NodeListField with an
            # is_empty method, rely on that
            if hasattr(f, 'is_empty'):
                if not f.is_empty():
                    return False
            # if this is a list or value field (int, string), check if empty
            elif not (f is None or f == '' or f == []):
                return False

        # no non-empty non-ignored fields were found - return True
        return True


class SympRelation(SympBase):
    '''Minimal wrapper for Symplectic-Elements relation being imported from OE'''

    ROOT_NAME = 'import-relationship'


    # Types of relations
    PUB_AUTHOR = 'publication-user-authorship'


    from_object = xmlmap.StringField("api:from-object")

    to_object = xmlmap.StringField("api:to-object")

    type_name = xmlmap.StringField("api:type-name")
    '''Relation type'''


class LastRun(models.Model):
    name = models.CharField(max_length=100)
    start_time = models.DateTimeField()

    def __unicode__(self):
        return "%s %s" % (self.name, self.start_time)
