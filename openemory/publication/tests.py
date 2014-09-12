# file openemory/publication/tests.py
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

import sys
from contextlib import contextmanager
import datetime
import json
import logging
import os
from cStringIO import StringIO
from datetime import date
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.auth.models import User, Permission, Group
from django.core.exceptions import ValidationError
from django.core import paginator, mail
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.core.management import call_command
from django.core.urlresolvers import reverse, resolve
from django.http import HttpResponse
from django.test import TestCase, Client
from django.template import context
from django.template.defaultfilters import filesizeformat
from django.utils.datastructures import SortedDict
from django.utils.unittest import skip
from eulfedora.server import Repository
from eulfedora.models import DigitalObject, FileDatastream
from eulfedora.util import RequestFailed
from eulfedora.rdfns import relsext, oai
from eulxml import xmlmap
from eulxml.xmlmap import mods, premis
from eullocal.django.emory_ldap.backends import EmoryLDAPBackend
from mock import patch, Mock, MagicMock
from pyPdf import PdfFileReader
from pyPdf.utils import PdfReadError
# from pdfminer.pdfparser import PDFParser, PDFDocument
# from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
# from pdfminer.pdfdevice import PDFDevice


from rdflib.graph import Graph as RdfGraph, Literal, RDF, URIRef
from urllib import urlencode, quote as urlquote

import openemory
from openemory.accounts.models import EsdPerson
from openemory.harvest.models import HarvestRecord
from openemory.publication.forms import UploadForm, ArticleModsEditForm, \
     validate_netid, AuthorNameForm, language_codes, language_choices, license_choices, FileTypeValidator, \
    SupplementalMaterialEditForm
from openemory.publication.models import NlmArticle, Article, ArticleMods,  \
     FundingGroup, AuthorName, AuthorNote, Keyword, FinalVersion, CodeList, \
     ResearchField, ResearchFields, NlmPubDate, NlmLicense, ArticlePremis, \
     ArticleStatistics, year_quarter, FeaturedArticle, SupplementalMaterial
from openemory.publication.forms import ArticleModsEditForm as amods
from openemory.publication import views as pubviews
from openemory.publication.management.commands.quarterly_stats_by_author import Command
from openemory.rdfns import DC, BIBO, FRBR

from openemory.publication.symp import SympAtom

from openemory.util import pmc_access_url, percent_match

# credentials for shared fixture accounts
from openemory.accounts.tests import USER_CREDENTIALS


from util import pdf_to_text


TESTUSER_CREDENTIALS = {'username': 'testuser', 'password': 't3st1ng'}
# NOTE: this user must be added test Fedora users xml file for tests to pass

pdf_filename = os.path.join(settings.BASE_DIR, 'publication', 'fixtures', 'test.pdf')
pdf_md5sum = '331e8397807e65be4f838ccd95787880'
pdf_full_text = '    \n \n This is a test PDF document. If you can read this, you have Adobe Acrobat Reader installed on your computer. '

pdf_filename_2 = os.path.join(settings.BASE_DIR, 'publication', 'fixtures', 'test2.pdf')
pdf_md5sum_2 = 'eb1aab81085889282ee61724a0a9b357'

lang_codelist_file = os.path.join(settings.BASE_DIR, 'publication',
                                  'fixtures', 'lang_codelist.xml')

logger = logging.getLogger(__name__)

class NlmArticleTest(TestCase):
    fixtures = ['site_admin_group', 'users']

    def setUp(self):
        # one corresponding author with an emory email
        path = os.path.join(settings.BASE_DIR, 'publication', 'fixtures', 'article-metadata.nxml')
        self.article = xmlmap.load_xmlobject_from_file(path, xmlclass=NlmArticle)

        # 4 emory authors, email in author instead of corresponding author info
        path = os.path.join(settings.BASE_DIR, 'publication', 'fixtures', 'article-full.nxml')
        self.article_multiauth = xmlmap.load_xmlobject_from_file(path, xmlclass=NlmArticle)

        # non-emory author
        path = os.path.join(settings.BASE_DIR, 'publication', 'fixtures', 'article-nonemory.nxml')
        self.article_nonemory = xmlmap.load_xmlobject_from_file(path, xmlclass=NlmArticle)

    def test_basic_fields(self):
        # test basic xmlobject field mapping
        self.assertEqual(self.article.docid, 2701312)
        self.assertEqual(self.article.pmid, 18446447)
        self.assertEqual(self.article.journal_title,
                         "Cardiovascular toxicology")
        self.assertEqual(self.article.article_title,
                         "Cardiac-Targeted Transgenic Mutant Mitochondrial Enzymes")
        self.assertEqual(len(self.article.authors), 17)
        self.assertEqual(self.article.authors[0].surname, 'Kohler')
        self.assertEqual(self.article.authors[0].given_names, 'James J.')
        self.assertTrue('Pathology, Emory' in self.article.authors[0].affiliation)
        self.assertEqual(self.article.authors[16].surname, 'Lewis')
        self.assertEqual(self.article.corresponding_author_emails[0], 'jjkohle@emory.edu')


        # affiliation referenced by xref/aff id
        self.assert_('Rehabilitation Medicine' in self.article_multiauth.authors[0].affiliation)

        # basic testing for license & permissions
        self.assert_(isinstance(self.article_multiauth.license, NlmLicense))
        self.assertEqual(u'Copyright \xA9 2005 Butler et al; licensee BioMed Central Ltd.',
                         self.article_multiauth.copyright)


    def test_fulltext_available(self):
        # special property based on presence/lack of body tag
        self.assertFalse(self.article.fulltext_available)
        self.assertTrue(self.article_multiauth.fulltext_available)

    def test_nlm_pubdate(self):
        self.assert_(self.article.publication_date)
        self.assertEqual('ppub', self.article.publication_date.type)
        self.assertEqual(2008, self.article.publication_date.year)
        self.assertEqual('2008', unicode(self.article.publication_date))

        self.assert_(self.article_multiauth.publication_date)
        self.assertEqual('epub', self.article_multiauth.publication_date.type)
        self.assertEqual(2005, self.article_multiauth.publication_date.year)
        self.assertEqual(5, self.article_multiauth.publication_date.month)
        self.assertEqual(31, self.article_multiauth.publication_date.day)
        self.assertEqual('2005-05-31', unicode(self.article_multiauth.publication_date))

    @patch('openemory.publication.models.EmoryLDAPBackend')
    def test_identifiable_authors(self, mockldap):
        mockldapinst = mockldap.return_value
        mockldapinst.find_user_by_email.return_value = (None, None)

        # this test relies on these users *not* being in the local db
        User.objects.filter(username='jjkohle').delete()
        User.objects.filter(username='swolf').delete()

        # test author with single corresponding emory author
        self.assertEqual([], self.article.identifiable_authors(),
            'should return an empty list when author not found in local DB or in LDAP')
        author_email = self.article.corresponding_author_emails[0]
        # ldap find by email should have been called
        mockldapinst.find_user_by_email.assert_called_with(author_email, False)
        # reset mock for next test
        mockldapinst.reset_mock()
        # by default, should cache values and not re-query ldap
        self.article.identifiable_authors()
        self.assertFalse(mockldapinst.find_user_by_email.called,
            'ldap should not be re-queried when requesting previously-populated author list')

        # reset, and use refresh option to reload with new mock test values
        mockldapinst.reset_mock()
        # create db user account for author - should be found & returned
        user = User(username='testauthor', email=author_email)
        user.save()
        self.assertEqual([user], self.article.identifiable_authors(refresh=True),
            'should return a list with User when author email is found in local DB')
        self.assertFalse(mockldapinst.find_user_by_email.called,
            'ldap should not be called when author is found in local db')

        # test multi-author article with email in author block
        self.assertEqual([], self.article_multiauth.identifiable_authors(),
            'should return an empty list when no authors are found in local DB or in LDAP')
        mockldapinst.reset_mock()
        # simulate returning a user account from ldap lookup
        usr = User()
        mockldapinst.find_user_by_email.return_value = (None, usr)
        self.assertEqual([usr for i in range(4)],  # article has 4 emory authors
                         self.article_multiauth.identifiable_authors(refresh=True),
            'should return an list of User objects initialized from LDAP')

        # make a list of all emails that were looked up in mock ldap
        # mock call args list: list of args, kwargs tuples - keep the first argument
        search_emails = [args[0] for args, kwargs in
                         mockldapinst.find_user_by_email.call_args_list]
        for auth in self.article_multiauth.authors:
            if auth.email and 'emory.edu' in auth.email:
                self.assert_(auth.email in search_emails)

        mockldapinst.reset_mock()
        # article has emory-affiliated authors, but no Emory emails
        self.assertEquals([], self.article_nonemory.identifiable_authors(),
             'article with no emory emails should return an empty list')
        self.assertFalse(mockldapinst.find_user_by_email.called,
             'non-emory email should not be looked up in ldap')


    @staticmethod
    def mock_find_by_email(email, derive=False):
        '''A mock implementation of
        :meth:`EmoryLDAPBackend.find_user_by_email`. Where the regular
        implementation looks a user up in LDAP, this mock implementation
        looks them up in the django auth users table.
        '''

        logger.debug('finding user for ' + email)
        try:
            username, at, host = email.partition('@')
            if host.lower() == 'emory.edu':
                user = User.objects.get(username=username.lower())
                logger.debug('found ' + user.username)
                return 'FAKE_DN', user
        except User.DoesNotExist:
            pass
        logger.debug('failed to find ' + email)
        return None, None

    @patch.object(EmoryLDAPBackend, 'find_user_by_email', new=mock_find_by_email)
    def test_as_article_mods(self):
        amods = self.article.as_article_mods()
        self.assertEqual(self.article.article_title, amods.title_info.title)
        self.assertEqual(self.article.article_subtitle, amods.title_info.subtitle)
        self.assertEqual('text', amods.resource_type)
        self.assertEqual('Article', amods.genre)
        self.assertEqual(unicode(self.article.abstract), amods.abstract.text)
        self.assertEqual(len(self.article.sponsors), len(amods.funders))
        self.assertEqual(self.article.sponsors[0], amods.funders[0].name)
        self.assertEqual(self.article.sponsors[1], amods.funders[1].name)
        self.assertEqual('doi:%s' % self.article.doi, amods.final_version.doi)
        # authors
        self.assertEqual(self.article.authors[0].surname,
                         amods.authors[0].family_name)
        self.assertEqual(self.article.authors[0].given_names,
                         amods.authors[0].given_name)
        self.assertEqual('Emory University', amods.authors[0].affiliation)
        # id should be matched from ldap look-up
        self.assertEqual('jjkohle', amods.authors[0].id)
        self.assertEqual(self.article.authors[1].surname,
                         amods.authors[1].family_name)
        self.assertEqual(self.article.authors[1].given_names,
                         amods.authors[1].given_name)
        self.assertEqual('Emory University', amods.authors[1].affiliation)
        # journal information
        self.assertEqual(self.article.journal_title, amods.journal.title)
        self.assertEqual(self.article.volume, amods.journal.volume.number)
        self.assertEqual(self.article.issue, amods.journal.number.number)
        self.assertEqual(self.article.first_page, amods.journal.pages.start)
        self.assertEqual(self.article.last_page, amods.journal.pages.end)
        self.assertEqual('2008', amods.publication_date)
        # keywords
        self.assertEqual(len(self.article.keywords), len(amods.keywords))
        for i in range(len(self.article.keywords)):
            self.assertEqual(self.article.keywords[i], amods.keywords[i].topic)
        # author notes
        self.assert_('e-mail: jjkohle@emory.edu' in amods.author_notes[0].text)

        # multiauth record has a publisher
        amods = self.article_multiauth.as_article_mods()
        self.assertEqual(self.article_multiauth.publisher, amods.journal.publisher)

        # plain-text formatting for readable abstract (sections/labels)
        # - internal section header - newlines
        self.assert_('\nMethods\nEach of ten'
                     in unicode(self.article_multiauth.abstract))
        # - two newlines between end of one section and beginning of next
        self.assert_('slope.\n\nResults'
                     in unicode(self.article_multiauth.abstract))
        # authors
        self.assertEqual(self.article_multiauth.authors[0].surname,
                         amods.authors[0].family_name)
        self.assertEqual(self.article_multiauth.authors[0].given_names,
                         amods.authors[0].given_name)
        self.assertEqual('Emory University', amods.authors[0].affiliation)
        self.assertEqual(self.article_multiauth.authors[1].surname,
                         amods.authors[1].family_name)
        self.assertEqual(self.article_multiauth.authors[1].given_names,
                         amods.authors[1].given_name)
        self.assertEqual(None, amods.authors[1].affiliation)
        # third author id should be matched from ldap look-up
        self.assertEqual('swolf', amods.authors[2].id)

        # license from license
        self.assertEqual(amods.license.text, self.article_multiauth.license.text)
        self.assertEqual(amods.license.link, self.article_multiauth.license.link)

        # license from coyright
        del self.article_multiauth.license
        self.article_multiauth.copyright= "this is a creative commons license statement"
        amods = self.article_multiauth.as_article_mods()
        self.assertEquals(amods.license.text, self.article_multiauth.copyright)
        
        # copyright
        self.assertEquals(amods.copyright.text, self.article_multiauth.copyright)

        # nonemory has additional author notes
        amods = self.article_nonemory.as_article_mods()
        self.assert_('Corresponding Author' in amods.author_notes[0].text)
        self.assert_('Present address' in amods.author_notes[1].text)
        self.assert_('Present address' in amods.author_notes[2].text)


class NlmLicenseTest(TestCase):
    _xlink_xmlns = 'xmlns:xlink="http://www.w3.org/1999/xlink" article-type="research-article"'
    LICENSE_FIXTURES = {
        'embedded_link': '''<license %s license-type="open-access">
    <license-p>Readers may use this
      article as long as the work is properly cited, the use is
      educational and not for profit, and the work is not altered. See
      <ext-link ext-link-type="uri" xlink:href="http://creativecommons.org/licenses/by-nc-nd/3.0/">http://creativecommons.org/licenses/by-nc-nd/3.0/</ext-link>
      for details.</license-p>
     </license>''' % _xlink_xmlns,

        'leading_comment': '''<license %s license-type="open-access"
  xlink:href="http://creativecommons.org/licenses/by/3.0">
    <license-p><!--CREATIVE COMMONS-->This article is an open-access
  article distributed under the terms and conditions of the Creative
  Commons Attribution license (<ext-link ext-link-type="uri"
  xlink:href="http://creativecommons.org/licenses/by/3.0/">http://creativecommons.org/licenses/by/3.0/</ext-link>).</license-p>
  </license>''' % _xlink_xmlns,

        'non_cc': '''<license %s>
   <p>Users may view, print, copy, download and text and data- mine the content in such documents, for the purposes of academic research, subject always to the full Conditions of use:
 <uri xlink:type="simple" xlink:href="http://www.nature.com/authors/editorial_policies/license.html#terms">http://www.nature.com/authors/editorial_policies/license.html#terms</uri></p>
</license>''' % _xlink_xmlns
    }

    def setUp(self):
        # full article has license info
        path = os.path.join(settings.BASE_DIR, 'publication', 'fixtures', 'article-full.nxml')
        self.article_multiauth = xmlmap.load_xmlobject_from_file(path, xmlclass=NlmArticle)
        self.license = self.article_multiauth.license

        # variant license formats
        self.embedded_link = xmlmap.load_xmlobject_from_string(self.LICENSE_FIXTURES['embedded_link'],
                                                               xmlclass=NlmLicense)
        self.leading_comment = xmlmap.load_xmlobject_from_string(self.LICENSE_FIXTURES['leading_comment'],
                                                               xmlclass=NlmLicense)
        self.non_cc = xmlmap.load_xmlobject_from_string(self.LICENSE_FIXTURES['non_cc'],
                                                               xmlclass=NlmLicense)
    def test_basic_fields(self):
        self.assertEqual('open-access', self.license.type)
        self.assertEqual('http://creativecommons.org/licenses/by/2.0',
                         self.license.link)

        # nested links (link not on license element)
        self.assertEqual('http://creativecommons.org/licenses/by-nc-nd/3.0/',
                         self.embedded_link.link)  # embedded ext-link
        self.assertEqual('http://www.nature.com/authors/editorial_policies/license.html#terms',
                         self.non_cc.link)	   # embedded uri

    def test_text(self):
        self.assert_('Open Access article distributed ' in self.license.text,
            'text should include content before ext-link')
        # article fixture repeats link url in ext-link within license text
        self.assert_(self.license.link in self.license.text,
            'text should include external link url')
        # text after the link
        self.assert_('use, distribution, and reproduction' in self.license.text,
            'text should include content after ext-link')

        # fixture with leading comment
        self.assert_('This article is an open-access' in self.leading_comment.text)
        self.assert_(self.leading_comment.link in self.leading_comment.text)
        self.assertEqual(1, self.leading_comment.text.count(self.leading_comment.link),
            'link should only be included in text once')
        self.assert_(').' in self.leading_comment.text) # text after ext-link

        # fixture with uri instead of ext-link
        self.assert_('Users may view, print, copy, download' in self.non_cc.text)
        self.assert_(self.non_cc.link in self.non_cc.text)
        self.assertEqual(1, self.non_cc.text.count(self.non_cc.link),
            'link should only be included in text once')

    def test_html(self):
        self.assert_('Open Access article distributed ' in self.license.html,
            'html should include content before ext-link')
        self.assert_('<a href="%(link)s">%(link)s</a>' % {'link': self.license.link}
                     in self.license.html,
            'html should include ext-link as a href')
        self.assert_('use, distribution, and reproduction' in self.license.html,
            'html should include content after ext-link')

        # fixture with leading comment
        self.assert_('This article is an open-access' in self.leading_comment.html)
        # note: link in license attribute differs from embeddded ext-link (trailing slash)
        self.assert_('<a href="%(link)s/">%(link)s/</a>' % {'link': self.leading_comment.link}
                     in self.leading_comment.html,
            'html should include ext-link as a href')
        self.assert_(').' in self.leading_comment.html) # text after ext-link

        # fixture with uri instead of ext-link
        self.assert_('Users may view, print, copy, download' in self.non_cc.html)
        self.assert_('<a href="%(link)s">%(link)s</a>' % {'link': self.non_cc.link}
                     in self.non_cc.html,
            'html should include uri link as a href')

    def test_creative_commons(self):
        self.assertEqual(True, self.license.is_creative_commons,
            'is_creative_commons should be true for license with CC url')
        self.assertEqual('by', self.license.cc_type,
            'CC license type should be "by" for %s' % self.license.link)

        self.assertEqual(True, self.embedded_link.is_creative_commons,
            'is_creative_commons should be true for license with CC url')
        expected = 'by-nc-nd'
        self.assertEqual(expected, self.embedded_link.cc_type,
            'CC license type should by "%s" for %s' % \
                         (expected, self.embedded_link.link))

        self.assertEqual(False, self.non_cc.is_creative_commons)
        self.assertEqual(None, self.non_cc.cc_type)


class ArticleTest(TestCase):

    def setUp(self):
        self.repo = Repository(username=settings.FEDORA_TEST_USER,
                                     password=settings.FEDORA_TEST_PASSWORD)
        # create a test article object to use in tests
        with open(pdf_filename) as pdf:
            self.article = self.repo.get_object(type=Article)
            self.article.label = 'A very scholarly article'
            self.article.dc.content.title = self.article.label
            self.article.dc.content.format = 'application/pdf'
            self.article.dc.content.type = 'TEXT'
            self.article.dc.content.description = 'Technical discussion of an esoteric subject'
            self.article.descMetadata.content.title = self.article.label
            self.article.pdf.content = pdf
            self.article.pdf.checksum = pdf_md5sum
            self.article.pdf.checksum_type = 'MD5'
            self.article.save()

        nxml_filename = os.path.join(settings.BASE_DIR, 'publication', 'fixtures', 'article-full.nxml')
        nxml = xmlmap.load_xmlobject_from_file(nxml_filename, xmlclass=NlmArticle)

        self.article_nlm = self.repo.get_object(type=Article)
        self.article_nlm.label = 'A snazzy article from PubMed'
        # set a mods field so that mods will be non-empty and get saved
        # (indexdata tests require mods datastream to exist in fedora)
        self.article_nlm.descMetadata.content.title = self.article_nlm.label
        self.article_nlm.contentMetadata.content = nxml
        self.article_nlm.save()

        self.pids = [self.article.pid, self.article_nlm.pid]

    def tearDown(self):
        for pid in self.pids:
            try:
                self.repo.purge_object(pid)
            except RequestFailed:
                logger.warn('Failed to purge test object %s' % pid)

    def test_number_of_pages(self):
        # simulate fedora error - exception should be caught & not propagated
        with patch.object(self.article, 'api') as mockapi:
            # create mockrequest to init RequestFailed
            mockrequest = Mock()
            mockrequest.status = 401
            mockrequest.reason = 'permission denied'
            mockapi.listDatastreams.side_effect = RequestFailed(mockrequest)
            self.assertEqual(None, self.article.number_of_pages)

        # normal behavior
        self.assertEqual(1, self.article.number_of_pages)

    def test_as_rdf(self):
        rdf = self.article.as_rdf()
        self.assert_(isinstance(rdf, RdfGraph))
        # check some of the triples
        self.assert_( (self.article.uriref, RDF.type, BIBO.AcademicArticle)
                      in rdf, 'rdf should include rdf:type of bibo:AcademicArticle')
        self.assert_( (self.article.uriref, RDF.type, FRBR.ScholarlyWork)
                      in rdf, 'rdf should include rdf:type of frbr:ScholarlyWork')
        self.assert_( (self.article.uriref, BIBO.numPages, Literal(1))
                      in rdf, 'rdf should include number of pages as bibo:numPages')
        # DC fields
        self.assert_( (self.article.uriref, DC.title, Literal(self.article.dc.content.title))
                      in rdf, 'rdf should include dc:title')
        self.assert_( (self.article.uriref, DC.type, Literal(self.article.dc.content.type))
                      in rdf, 'rdf should include dc:type')
        self.assert_( (self.article.uriref, DC.description,
                       Literal(self.article.dc.content.description))
                      in rdf, 'rdf should include dc:description')

    def test_index_data(self):
        idxdata = self.article.index_data()

        self.assertFalse('embargo_end' in idxdata,
                         'embargo_end date should not be set')

        self.assertEqual(idxdata['fulltext'].split(), pdf_full_text.split(),
                         'article index data should include pdf text')

        idxdata = self.article_nlm.index_data()
        self.assertTrue('transcranial magnetic stimulation' in idxdata['fulltext'],
                        'article index data should include nlm body')
        self.assertTrue('interhemispheric variability' in idxdata['abstract'],
                        'article index data should include nlm abstract')

        # minimal MODS - missing fields should not be set in index data
        # - unreviewed record; no review date
        amods = self.article_nlm.descMetadata.content
        amods.title = 'Capitalism and the Origins of the Humanitarian Sensibility'
        idxdata = self.article_nlm.index_data()
        for field in ['funder', 'journal_title', 'journal_publisher', 'keywords',
                      'author_notes', 'pubdate', 'pubyear', 'language',
                      'review_date']:
            self.assert_(field not in idxdata)
        # abstract should be set from NLM, since not available in MODS
        self.assertTrue('interhemispheric variability' in idxdata['abstract'],
                        'article index data should include nlm abstract')

        # MODS fields -- all indexed fields
        amods.funders.extend([FundingGroup(name='Mellon Foundation'),
                              FundingGroup(name='NSF')])
        amods.create_journal()
        amods.journal.title = 'The American Historical Review'
        amods.journal.publisher = 'American Historical Association'
        amods.create_abstract()
        amods.abstract.text = 'An unprecedented wave of humanitarian reform ...'
        amods.keywords.extend([Keyword(topic='morality'), Keyword(topic='humanitarian reform')])
        amods.subjects.extend([ResearchField(id="id1", topic='General Studies'),
                               ResearchField(id="id2", topic='Specific Studies')])
        amods.author_notes.append(AuthorNote(text='First given at AHA 1943'))
        amods.publication_date = '2001-05-29'
        amods.language = 'English'
        amods.authors.append(AuthorName(family_name='SquarePants',
                                        given_name='SpongeBob',
                                        affiliation='Nickelodeon'))
        idxdata = self.article_nlm.index_data()
        self.assertEqual(idxdata['title'], amods.title)
        self.assertEqual(len(amods.funders), len(idxdata['funder']))
        for fg in amods.funders:
            self.assert_(fg.name in idxdata['funder'])
        self.assertEqual(idxdata['journal_title'], amods.journal.title)
        self.assertEqual(idxdata['journal_publisher'], amods.journal.publisher)
        self.assertEqual(idxdata['abstract'], amods.abstract.text)
        self.assertEqual(len(amods.keywords), len(idxdata['keyword']))
        for kw in amods.keywords:
            self.assert_(kw.topic in idxdata['keyword'])
        self.assertEqual(len(amods.subjects), len(idxdata['researchfield_id']))
        self.assertEqual(len(amods.subjects), len(idxdata['researchfield']))
        for rf in amods.subjects:
            self.assert_(rf.id in idxdata['researchfield_id'])
            self.assert_(rf.topic in idxdata['researchfield'])
        self.assertEqual([amods.author_notes[0].text], idxdata['author_notes'])
        self.assertEqual('2001', idxdata['pubyear'])
        self.assertEqual(amods.publication_date, idxdata['pubdate'])
        self.assertEqual([amods.language], idxdata['language'])
        self.assertEqual(len(amods.authors), len(idxdata['creator']))
        self.assertEqual(len(amods.authors), len(idxdata['author_affiliation']))
        for auth in amods.authors:
            expect_name = '%s, %s' % (auth.family_name, auth.given_name)
            self.assert_(expect_name in idxdata['creator'])
            self.assert_(auth.affiliation in idxdata['author_affiliation'])

        # add review event
        self.article.provenance.content.create_object()
        self.article.provenance.content.object.type = 'p:representation'
        self.article.provenance.content.object.id_type = 'pid'
        self.article.provenance.content.object.id = self.article.pid
        ev = premis.Event()
        ev.id_type = 'local'
        ev.id = '%s.ev01' % self.article.pid
        ev.type = 'review'
        ev.date = '2006-06-06T00:00:00.001'
        ev.detail = 'reviewed by Ann Admynn'
        ev.agent_type = 'netid'
        ev.agent_id = 'aadmyn'
        self.article.provenance.content.events.append(ev)
        # save to create provenance datastream
        self.article.save()
        idxdata = self.article.index_data()
        self.assertEqual(ev.date, idxdata['review_date'])

        #make article embargoed
        embargo_end = datetime.datetime.now() + datetime.timedelta(days=1)
        embargo_end = embargo_end.strftime("%Y-%m-%d")
        self.article.descMetadata.content.embargo_end = embargo_end
        self.article.save()
        idxdata = self.article.index_data()

        self.assertFalse('fulltext' in idxdata,
            'article index data should not include pdf text because the article is embargoed')
        self.assertTrue('embargo_end' in idxdata,
            'embargo_end date should not be set')

    @patch.object(DigitalObject, 'save')
    def test_save(self, mockdigobjsave):
        mockapi = Mock()
        original_owner = 'uploader'
        article = Article(mockapi)
        article.owner = original_owner
        # no authors in mods - owner should not be changed
        article.save()
        self.assertEqual(original_owner, article.owner)

        amods = article.descMetadata.content
        amods.authors.extend([AuthorName(family_name='SquarePants',
                                         given_name='SpongeBob',
                                         affiliation='Nickelodeon'),
                              AuthorName(family_name='Mouse',
                                         given_name='Mickey',
                                         id='mmouse'),
                              AuthorName(family_name='Duck',
                                         given_name='Daffy',
                                         id='dduck'),
                              AuthorName(family_name='Wayne',
                                         given_name='Bruce',
                                         id='batman'),
                              ])
        article.save()
        self.assertEqual('mmouse,dduck,batman', article.owner,
            'article owner should contain all author ids from MODS')

    def test_embargo_end_date(self):
        obj = Article(Mock())  # mock api
        self.assertEqual(None, obj.embargo_end_date,
            'embargo_end_date property should be None when no embargo_end is set in mods')
        obj.descMetadata.content.embargo_end = '2015-03-21'
        self.assert_(isinstance(obj.embargo_end_date, date),
            'embargo_end_date should be an instance of datetime.date')
        self.assertEqual(date(2015, 3, 21), obj.embargo_end_date)

    def test_is_embargoed(self):
        obj = Article(Mock())  # mock api
        # no embargo date - should return false (not embargoed)
        self.assertFalse(obj.is_embargoed)
        # embargo end date in the future - should be true
        nextyear = date.today() + relativedelta(years=1)
        obj.descMetadata.content.embargo_end = nextyear.isoformat()
        self.assertTrue(obj.is_embargoed)
        # embargo date in the past - should be false
        lastyear = date.today() + relativedelta(years=-1)
        obj.descMetadata.content.embargo_end = lastyear.isoformat()
        self.assertFalse(obj.is_embargoed)

    def test_pdf_cover(self):
        # add additional metadata to test cover page contents
        amods = self.article.descMetadata.content
        amods.authors.extend([AuthorName(family_name='Mouse',
                                        given_name='Minnie', id='mmouse',
                                        affiliation='Emory University'),
                              AuthorName(family_name='Science',
                                        given_name='Joe',
                                        affiliation='GA Tech')])
        amods.create_journal()
        amods.journal.title = 'Collected Scholarly Works'
        amods.ark_uri = 'http://a.rk/ark:/1/b'
        amods.create_final_version()
        amods.final_version.url = 'http://fin.al/versi.on'
        amods.final_version.doi = 'doi:10.1/an-article'
        #amods.locations.append(mods.Location(url='http://othe.er/versi.on'))
        amods.keywords.extend([Keyword(topic='mice'), Keyword(topic='bioscience')])
        amods.subjects.append(ResearchField(topic='Biographical Sciences'))

        # generate the cover and inspect it with pyPdf reader
        pdfcover = self.article.pdf_cover()
        pdfreader = PdfFileReader(pdfcover)
        self.assert_(pdfreader,
                     'pdf cover file should be readable by pyPdf.PdfFileReader')
        self.assertEqual(1, pdfreader.getNumPages(),
             'cover page PDF document should have only 1 page')

        # extract the text from the page of the pdf to check contents
        covertext = pdfreader.pages[0].extractText()
        self.assert_(amods.title in covertext,
            'cover page should include article title')
        self.assert_('%s %s' % (amods.authors[0].given_name,
                                amods.authors[0].family_name) in covertext,
            'cover page should include first author name')
        self.assert_('%s %s' % (amods.authors[1].given_name,
                                amods.authors[1].family_name) in covertext,
            'cover page should include second author name')
        self.assert_(amods.authors[0].affiliation in covertext,
            'cover page should include author affiliation')
        self.assert_(amods.journal.title in covertext,
            'cover page should include journal title')
        # ARK
        self.assert_(amods.ark_uri in covertext,
            'cover page should include ARK url')
        # final version, doi, other version
        self.assert_(amods.final_version.url in covertext,
            'cover page should include final version URL')
        self.assert_(amods.final_version.doi in covertext,
            'cover page should include final version DOI')
        #self.assert_(amods.locations[0].url in covertext,
        #    'cover page should include other version URL')

        # inspect docinfo attributes - set from article metadata
        docinfo = pdfreader.documentInfo
        self.assertEqual(self.article.descMetadata.content.title,
                         docinfo.title,
            'document title should be set based on article title')
        self.assertEqual(', '.join('%s %s' % (a.given_name, a.family_name) for a in amods.authors),
                         docinfo.author,
            'document authors should list all author names')
        self.assertEqual('; '.join(s.topic for s in amods.subjects),
                         docinfo.subject,
            'document subject should list all metadata subjects/research fields')
        # NOTE: keywords is not exposed in docinfo interface, but is being set
        self.assertEqual('; '.join(kw.topic for kw in amods.keywords),
                         docinfo['/Keywords'],
            'document keywords should list all metadata keywords')

    def test_year_quarter(self):
        #test all valid values
        self.assertEqual(1, year_quarter(1))
        self.assertEqual(1, year_quarter(2))
        self.assertEqual(1, year_quarter(3))
        self.assertEqual(2, year_quarter(4))
        self.assertEqual(2, year_quarter(5))
        self.assertEqual(2, year_quarter(6))
        self.assertEqual(3, year_quarter(7))
        self.assertEqual(3, year_quarter(8))
        self.assertEqual(3, year_quarter(9))
        self.assertEqual(4, year_quarter(10))
        self.assertEqual(4, year_quarter(11))
        self.assertEqual(4, year_quarter(12))

        #test values outside month range
        self.assertRaisesRegexp(ValueError, 'Month must be between 1 and 12', year_quarter, 0)
        self.assertRaisesRegexp(ValueError, 'Month must be between 1 and 12', year_quarter, 13)



    def test__mods_to_dc(self):
        article  = Article(Mock())
        mods = article.descMetadata.content
        dc = article.dc.content

        # test with no fields set
        article._mods_to_dc()

        article.pid = 'test:123'
        article.label = "Test Object"
        mods.create_title_info()
        mods.title_info.title = "Cool Title"
        mods.title_info.subtitle = "Absolute Zero"
        mods.authors.append(AuthorName(given_name="Joe", family_name="Smith"))
        mods.authors.append(AuthorName(given_name="Jim", family_name="Jones"))
        mods.version = "Good Version"
        mods.language = 'eng'
        mods.create_physical_description()
        mods.physical_description.media_type = "application/pdf"
        mods.create_abstract()
        mods.abstract.text = "The Abstract"
        mods.subjects.extend([ResearchField(id="id1", topic='Advanced Studies')])
        mods.keywords.extend([Keyword(id="id2", topic='Fun')])
        mods.create_final_version()
        mods.ark_uri ="http://perm/link/"
        mods.publication_date = "2012-12-21"
        mods.create_journal()
        mods.journal.title = "I am Published"
        mods.journal.publisher = 'Pub'
        mods.journal.create_volume()
        mods.journal.volume.number = 10
        mods.journal.create_number()
        mods.journal.number.number = 20
        mods.journal.create_pages()
        mods.journal.pages.start = '2'
        mods.journal.pages.end = '5'
        mods.embargo = "100 bizillion years (or longer if possible)"
        mods.create_license()
        mods.license.text = "You can not use this for any reason whatsoever."

        article._mods_to_dc()
        title =  "%s: %s" % (mods.title_info.title, mods.title_info.subtitle)
        self.assertEquals(title,  dc.title)
        self.assertTrue("Joe Smith" in dc.contributor_list)
        self.assertTrue("Jim Jones" in dc.contributor_list)
        self.assertEqual('text', dc.type_list[0])
        self.assertEqual('%s: %s' % (mods.version, 'article'),  dc.type_list[1])
        self.assertEquals(dc.language, mods.language)
        self.assertEquals(dc.format, mods.physical_description.media_type)
        self.assertEquals(mods.abstract.text, dc.description)
        self.assertTrue('Advanced Studies' in dc.subject_list)
        self.assertTrue('Fun' in dc.subject_list)
        source = '%s Volume %s Issue %s Date %s Pages %s-%s' % (mods.journal.title, mods.journal.volume.number,
                                                                mods.journal.number.number, mods.publication_date,
                                                                mods.journal.pages.start, mods.journal.pages.end)
        self.assertEquals(source,  dc.source)

    def test__prep_dc_for_oai(self):
        dc = self.article.dc.content.node
        self.assertTrue('xsi' in dc.nsmap)
        self.assertTrue('{%s}%s' % (dc.nsmap['xsi'], 'schemaLocation') in dc.attrib)

        self.article._prep_dc_for_oai()

        dc = self.article.dc.content.node
        self.assertFalse('xsi' in dc.nsmap)
        self.assertEqual(len(dc.attrib), 0)

    def test_as_symp(self):
        # Add additional fields to article
        self.article.descMetadata.content.create_abstract()
        self.article.descMetadata.content.abstract.text = "Interesting Abstract"
        self.article.descMetadata.content.create_final_version()
        self.article.descMetadata.content.final_version.doi = "10:/12345"
        self.article.descMetadata.content.create_journal()
        self.article.descMetadata.content.journal.create_volume()
        self.article.descMetadata.content.journal.volume.number = 1
        self.article.descMetadata.content.journal.create_number()
        self.article.descMetadata.content.journal.number.number = 2
        self.article.descMetadata.content.journal.title = "Journal of Boring Articles"
        self.article.descMetadata.content.journal.publisher = "Clearing House"
        self.article.descMetadata.content.publication_date = "2014-01-02"
        self.article.dc.content.identifier_list.append("PMC12345")
        self.article.descMetadata.content.language = "English"
        k1 = Keyword()
        k1.topic = "Thing 1"
        k2 = Keyword()
        k2.topic = "Thing 2"
        self.article.descMetadata.content.keywords.extend([k1, k2])
        a1 = AuthorNote()
        a1.text = "My Note 1"
        a2 = AuthorNote()
        a2.text = "My Note 2"
        self.article.descMetadata.content.author_notes.extend([a1,a2])
        n1 = AuthorName()
        n1.id = 'n1'
        n1.family_name = "Smith"
        n1.given_name = "Jim"
        n2 = AuthorName()
        n2.id = 'n2'
        n2.family_name = "Jones"
        n2.given_name = "John"
        self.article.descMetadata.content.authors.extend([n1, n2])

        pub, relations = self.article.as_symp()

        self.assertEqual(pub.type_id, '5')
        self.assertEqual(pub.types, ['Article'])
        self.assertEqual(pub.title, self.article.descMetadata.content.title_info.title)
        self.assertEqual(pub.abstract, self.article.descMetadata.content.abstract.text)
        self.assertEqual(pub.doi, self.article.descMetadata.content.final_version.doi)
        self.assertEqual(pub.volume, self.article.descMetadata.content.journal.volume.number)
        self.assertEqual(pub.issue, self.article.descMetadata.content.journal.number.number)
        self.assertEqual(pub.journal, self.article.descMetadata.content.journal.title)
        self.assertEqual(pub.publisher, self.article.descMetadata.content.journal.publisher)
        self.assertEqual(pub.publication_date.day, "2")
        self.assertEqual(pub.publication_date.month, "1")
        self.assertEqual(pub.publication_date.year, "2014")
        self.assertEqual(pub.pmcid, "PMC%s" % self.article.pmcid)
        self.assertEqual(pub.language, self.article.descMetadata.content.language)
        self.assertEqual(pub.keywords, ['Thing 1', 'Thing 2'])
        self.assertEqual(pub.authors[0].last_name, 'Smith')
        self.assertEqual(pub.authors[0].initials, 'JS')
        self.assertEqual(pub.authors[1].last_name, 'Jones')
        self.assertEqual(pub.authors[1].initials, 'JJ')

        self.assertEqual(relations[0].from_object, 'publication(source-manual,pid-%s)' % self.article.pid)
        self.assertEqual(relations[0].to_object, "user(username-%s)" % "n1")
        self.assertEqual(relations[0].type_name, 'publication-user-authorship')
        self.assertEqual(relations[1].from_object, 'publication(source-manual,pid-%s)' % self.article.pid)
        self.assertEqual(relations[1].to_object, "user(username-%s)" % "n2")
        self.assertEqual(relations[1].type_name, 'publication-user-authorship')


    def test_from_symp(self):
        sympAtom_file = os.path.join(settings.BASE_DIR, 'publication', 'fixtures', 'SympAtom.xml')
        self.article.sympAtom.content = xmlmap.load_xmlobject_from_file(sympAtom_file, xmlclass=SympAtom)
        self.article.from_symp()
        mods = self.article.descMetadata.content

        self.assertEqual(self.article.label, 'Recombinant TLR5 Agonist CBLB502 Promotes NK Cell-Mediated Anti-CMV Immunity in Mice')
        self.assertTrue(self.article.has_model(Article.ARTICLE_CONTENT_MODEL))
        self.assertEqual(self.article.descMetadata.label, 'descMetadata(MODS)')
        self.assertEqual(self.article.owner, 'ewaller')

        self.assertEqual(mods.resource_type, 'text')
        self.assertEqual(mods.genre, 'Article')
        self.assertEqual(mods.ark_uri,  '%sark:/25593/%s' % (settings.PIDMAN_HOST, self.article.pid.split(':')[1]))
        self.assertEqual(mods.ark, 'ark:/25593/%s' % (self.article.pid.split(':')[1]))
        self.assertEqual(mods.title, 'Recombinant TLR5 Agonist CBLB502 Promotes NK Cell-Mediated Anti-CMV Immunity in Mice')
        self.assertEqual(mods.language, "English")
        self.assertEqual(mods.language_code, "eng")
        self.assertTrue(mods.abstract.text.startswith('Prior work using allogeneic bone marrow'))
        self.assertEqual(mods.journal.volume.number, '9')
        self.assertEqual(mods.journal.number.number, '5')
        self.assertEqual(mods.publication_date, '2014-05-30')
        self.assertEqual(mods.journal.pages.start, 'e96165')
        self.assertEqual(mods.journal.pages.end, 'e96165')
        self.assertEqual(mods.journal.publisher, 'PUBLIC LIBRARY SCIENCE')
        self.assertEqual(mods.journal.title, 'PLOS ONE')
        self.assertEqual(mods.final_version.doi, '10.1371/journal.pone.0096165')
        self.assertEqual(mods.final_version.url, 'http://dx.doi.org/10.1371/journal.pone.0096165')
        self.assertEqual(mods._embargo, "No embargo")
        self.assertEqual(mods.keywords[0].topic, 'Science & Technology')
        self.assertEqual(mods.authors[0].id, 'ewaller')
        self.assertEqual(mods.authors[0].family_name, 'Waller')
        self.assertEqual(mods.authors[0].given_name, 'Edmund')
class ValidateNetidTest(TestCase):
    fixtures =  ['testusers']

    @patch('openemory.publication.forms.EmoryLDAPBackend')
    def test_validate_netid(self, mockldap):
        # db username - no validation error
        validate_netid(TESTUSER_CREDENTIALS['username'])
        mockldap.return_value.find_user.assert_not_called
        # mock ldap valid response
        mockldap.return_value.find_user.return_value = ('userdn', 'username')
        validate_netid('ldapuser')
        mockldap.return_value.find_user.assert_called
        # mock ldap - not found
        mockldap.return_value.find_user.return_value = (None, None)
        self.assertRaises(ValidationError, validate_netid, 'noldapuser')

class AuthorNameFormTest(TestCase):
    def setUp(self):
        self.form = AuthorNameForm()
        self.form.cleaned_data = {}

    def test_clean(self):
        # no data - no exception
        self.form.clean()

        # netid but no affiliation
        self.form.cleaned_data['id'] = 'netid'
        self.assertRaises(ValidationError, self.form.clean)

        # affiliation but no netid - fine
        del self.form.cleaned_data['id']
        self.form.cleaned_data['affiliation'] = 'GA Tech'
        self.form.clean()



class PublicationViewsTest(TestCase):
    multi_db = True
    fixtures =  ['site_admin_group', 'testusers', 'users', 'esdpeople', 'teststats']

    def setUp(self):
        self.repo = Repository(username=settings.FEDORA_TEST_USER,
                                     password=settings.FEDORA_TEST_PASSWORD)
        self.admin_repo = Repository(username=settings.FEDORA_MANAGEMENT_USER,
                                     password=settings.FEDORA_MANAGEMENT_USER)
        self.client = Client()

        # create a test article object to use in tests
        with open(pdf_filename) as pdf:
            self.article = self.repo.get_object(type=Article)
            self.article.label = 'A very scholarly article'
            self.article.owner = TESTUSER_CREDENTIALS['username']
            self.article.pdf.content = pdf
            self.article.pdf.checksum = pdf_md5sum
            self.article.pdf.checksum_type = 'MD5'
            # descriptive metadata
            self.article.descMetadata.content.title = 'A very scholarly article'
            self.article.descMetadata.content.create_abstract()
            self.article.descMetadata.content.abstract.text = 'An overly complicated description of a very scholarly article'
            # self.article.dc.content.creator_list.append("Jim Smith")
            # self.article.dc.content.contributor_list.append("John Smith")
            # self.article.dc.content.date = "2011-08-24"
            # self.article.dc.content.language = "english"
            self.article.descMetadata.content.create_journal()
            self.article.descMetadata.content.journal.publisher = "Big Deal Publications"
            self.article.save()

        self.pids = [self.article.pid]

        self.itemID_relation = (self.article.uriref, oai.itemID, Literal("oai:ark:/25593/%s" % self.article.pid.split(":")[1]))

        # user fixtures needed for profile links
        self.coauthor_username = 'mmouse'
        self.coauthor_user = User.objects.get(username=self.coauthor_username)
        self.coauthor_esd = EsdPerson.objects.get(
                netid='MMOUSE')

        self.coll = URIRef(settings.PID_ALIASES['oe-collection'])

    def tearDown(self):
        for pid in self.pids:
            try:
                self.repo.purge_object(pid)
            except RequestFailed:
                logger.warn('Failed to purge test object %s' % pid)

    def test_ingest_upload(self):
        # not logged in
        upload_url = reverse('publication:ingest')
        response = self.client.get(upload_url)
        expected, got = 401, response.status_code
        self.assertEqual(expected, got, 'Expected %s but got %s for GET on %s (not logged in)' % \
                         (expected, got, upload_url))
        response = self.client.post(upload_url)
        expected, got = 401, response.status_code
        self.assertEqual(expected, got, 'Expected %s but got %s for POST on %s (not logged in)' % \
                         (expected, got, upload_url))

        # login as test user
        # -  use custom login so user credentials will be used for fedora access
        self.client.post(reverse('accounts:login'), TESTUSER_CREDENTIALS)
        response = self.client.get(upload_url)
        expected, got = 200, response.status_code
        self.assertEqual(expected, got, 'Expected %s but got %s for GET on %s' % \
                         (expected, got, upload_url))
        self.assert_(isinstance(response.context['form'], UploadForm),
                     'upload form should be set in response context on GET')
        # no legal selection in response
        self.assertNotContains(response, 'Mediated Deposit')
        # invalid post - no file
        response = self.client.post(upload_url)
        self.assertContains(response, 'A PDF file is required to submit an article.',
             msg_prefix='required field message should be displayed when the form is submitted without data')

        # test with valid pdf but no assent
        with open(pdf_filename) as pdf:
            response = self.client.post(upload_url, {'pdf': pdf, 'assent': False})
            self.assertContains(response, 'must indicate assent to upload',
                msg_prefix='if assent is not selected, form is not valid and ' +
                            'error message indicates why it is required')

        # test with non-pdf
        xmlpath = os.path.join(settings.BASE_DIR, 'publication', 'fixtures', 'article-metadata.nxml')
        with open(xmlpath) as xml:
            response = self.client.post(upload_url, {'pdf': xml, 'assent': True})
            self.assertContains(response, 'not a valid PDF',
                msg_prefix='error message for uploading non-pdf')

        # POST a test pdf
        with open(pdf_filename) as pdf:
            response = self.client.post(upload_url, {'pdf': pdf, 'assent': True})
            expected, got = 303, response.status_code
            self.assertEqual(expected, got,
                'Should redirect on successful upload; expected %s but returned %s for %s' \
                             % (expected, got, upload_url))
            # check redirect location
            redirect_path = response['Location'][len('https://testserver')-1:]
            resolve_match = resolve(redirect_path)
            self.assertEqual(pubviews.edit_metadata, resolve_match.func,
                 'ingest should redirect to edit metadata view on success')
            pid = resolve_match.kwargs['pid']
            self.pids.append(pid)	# add to list for clean-up in tearDown

            # make another request to get messages
            response = self.client.get(upload_url)
            messages = [ str(msg) for msg in response.context['messages'] ]
            msg = messages[0]
            self.assert_(msg.startswith('Success! Your article was uploaded.'),
                         "successful save message set in response context")
            self.assert_('Please complete the required fields in Citation Information and submit.' in msg,
                         "edit metadata instruction included in success message")

        # inspect created object
        obj = self.repo.get_object(pid, type=Article)
        # check object initialization
        self.assertEqual('test.pdf', obj.label)
        self.assertEqual('test.pdf', obj.dc.content.title)
        self.assertEqual(TESTUSER_CREDENTIALS['username'], obj.owner)
        self.assertEqual('I', obj.state,
                         'uploaded record should be ingested as inactive')
        self.assertEqual('application/pdf', obj.pdf.mimetype)
        self.assertTrue((obj.uriref, relsext.isMemberOfCollection, self.coll)  in obj.rels_ext.content)
        # pdf contents
        with open(pdf_filename) as pdf:
            self.assertEqual(pdf.read(), obj.pdf.content.read())
        # checksum
        self.assertEqual(pdf_md5sum, obj.pdf.checksum)
        self.assertEqual('MD5', obj.pdf.checksum_type)
        # static mods values
        self.assertEqual('text', obj.descMetadata.content.resource_type)
        self.assertEqual('Article', obj.descMetadata.content.genre)
        self.assertEqual('application/pdf', obj.descMetadata.content.physical_description.media_type)
        # user set as author in mods
        testuser = User.objects.get(username=TESTUSER_CREDENTIALS['username'])
        self.assertEqual(1, len(obj.descMetadata.content.authors))
        self.assertEqual(testuser.username, obj.descMetadata.content.authors[0].id)
        self.assertEqual(testuser.last_name, obj.descMetadata.content.authors[0].family_name)
        self.assertEqual(testuser.first_name, obj.descMetadata.content.authors[0].given_name)
        self.assertEqual('Emory University', obj.descMetadata.content.authors[0].affiliation)

        #check upload premis event
        self.assertEqual("%s.ev001" % obj.pid, obj.provenance.content.upload_event.id)
        self.assertEqual('upload', obj.provenance.content.upload_event.type)
        self.assertTrue(obj.provenance.content.date_uploaded)
        self.assertEqual(TESTUSER_CREDENTIALS['username'], obj.provenance.content.upload_event.agent_id)
        self.assertTrue('upon assent to deposit' in obj.provenance.content.upload_event.detail)
        self.assertTrue(openemory.__version__ in obj.provenance.content.upload_event.detail)

        # confirm that logged-in site user appears in fedora audit trail
        xml, uri = obj.api.getObjectXML(obj.pid)
        self.assert_('<audit:responsibility>%s</audit:responsibility>' \
                     % TESTUSER_CREDENTIALS['username'] in xml)

        # test ingest error with mock
        mock_article = Mock(Article)
        mock_article.return_value = mock_article  # return self on init
        # create mockrequest to init RequestFailed
        mockrequest = Mock()
        mockrequest.status = 401
        mockrequest.reason = 'permission denied'
        mock_article.save.side_effect = RequestFailed(mockrequest)
        with patch('openemory.publication.views.Article', new=mock_article):
            with open(pdf_filename) as pdf:
                response = self.client.post(upload_url, {'pdf': pdf, 'assent': True})
                self.assertContains(response, 'error uploading your document')
                messages = [ str(msg) for msg in response.context['messages'] ]
                self.assertEqual(0, len(messages),
                    'no success messages set when ingest errors')

        # add testuser to site admin group for remaining tests
        testuser = User.objects.get(username=TESTUSER_CREDENTIALS['username'])
        testuser.groups.add(Group.objects.get(name='Site Admin'))
        testuser.save()

        # admin gets legal statement selection
        response = self.client.get(upload_url)
        self.assertContains(response, 'Mediated Deposit')

        # POST a mediated test pdf
        with open(pdf_filename) as pdf:
            response = self.client.post(upload_url,
                    {'pdf': pdf, 'assent': True, 'legal_statement': 'MEDIATED'})
            # get pid of result object
            redirect_path = response['Location'][len('https://testserver')-1:]
            resolve_match = resolve(redirect_path)
            pid = resolve_match.kwargs['pid']
            self.pids.append(pid)	# add to list for clean-up in tearDown

            # make another request to get messages
            response = self.client.get(upload_url)
            # ignore them: they're tested above

        # inspect created object
        obj = self.repo.get_object(pid, type=Article)
        # user is *not* an author
        mods_author_ids = [a.id for a in obj.descMetadata.content.authors]
        self.assertFalse(TESTUSER_CREDENTIALS['username'] in mods_author_ids)
        # note that an object has to have an owner in fedora, so the ingest
        # has no option but to set the active user as the owner until a
        # better one is found.
        #self.assertFalse(TESTUSER_CREDENTIALS['username'] in obj.owner)

        #check upload premis event
        self.assertEqual(TESTUSER_CREDENTIALS['username'], obj.provenance.content.upload_event.agent_id)
        self.assertTrue('Mediated Deposit' in obj.provenance.content.upload_event.detail)
        self.assertTrue(openemory.__version__ in obj.provenance.content.upload_event.detail)

        self.assertTrue((obj.uriref, relsext.isMemberOfCollection, self.coll)  in obj.rels_ext.content)

    def test_ingest_from_harvestrecord(self):
        # test ajax post to ingest from havest queue

        # not logged in
        ingest_url = reverse('publication:ingest')
        response = self.client.post(ingest_url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        expected, got = 401, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for %s (not logged in)' \
                % (expected, got, ingest_url))

        # login as test user for remaining tests
        self.client.post(reverse('accounts:login'), TESTUSER_CREDENTIALS)
        response = self.client.post(ingest_url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        expected, got = 403, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for %s (non site-admin)' \
                % (expected, got, ingest_url))

        # add testuser to site admin group for remaining tests
        testuser = User.objects.get(username=TESTUSER_CREDENTIALS['username'])
        testuser.groups.add(Group.objects.get(name='Site Admin'))
        testuser.save()

        # no post data  - bad request
        response = self.client.post(ingest_url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        expected, got = 400, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for %s (no data posted)' \
                % (expected, got, ingest_url))
        self.assertContains(response, 'No record specified', status_code=expected)
        # post data but no id - bad request
        response = self.client.post(ingest_url, {'pmcid': ''},
                                    HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        expected, got = 400, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for %s (no pmcid posted)' \
                % (expected, got, ingest_url))
        self.assertContains(response, 'No record specified', status_code=expected)
        # invalid record id - 404
        response = self.client.post(ingest_url, {'pmcid': '1'},
                                    HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        expected, got = 404, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for %s (invalid pmcid)' \
                % (expected, got, ingest_url))

        # create a record to test ingesting
        record = HarvestRecord(pmcid=2001, title='Test Harvest Record')
        record.save()
        # add test user as record author
        record.authors = [User.objects.get(username=TESTUSER_CREDENTIALS['username'])]
        record.save()

        response = self.client.post(ingest_url, {'pmcid': record.pmcid},
                                    HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        expected, got = 201, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for %s (valid pmcid)' \
                % (expected, got, ingest_url))
        self.assertTrue('Location' in response,
            '201 Created response should have a Location header')
        # check redirect location
        redirect_path = response['Location'][len('https://testserver')-1:]
        resolve_match = resolve(redirect_path)
        self.assertEqual(pubviews.view_article, resolve_match.func,
                 'ingest location should be record display page on success')

        # harvest record should have been updated
        record = HarvestRecord.objects.get(pmcid=record.pmcid)  # fresh copy
        self.assertEqual('ingested', record.status,
            'db record status should be set to "ingested" after successful ingest')

        # get the newly created pid from the response, for inspection
        resp_info = response.content.split()
        pid = resp_info[-1].strip()
        self.pids.append(pid)	# add to list for clean-up

        # basic sanity-checking on the object (record->article method tested elsewhere)
        newobj = self.admin_repo.get_object(pid, type=Article)
        self.assertEqual(newobj.label, record.title)
        self.assertEqual(newobj.owner, record.authors.all()[0].username)
        #check harvest premis event
        self.assertEqual("%s.ev001" % newobj.pid, newobj.provenance.content.harvest_event.id)
        self.assertEqual('harvest', newobj.provenance.content.harvest_event.type)
        self.assertTrue(newobj.provenance.content.date_harvested)
        self.assertEqual(TESTUSER_CREDENTIALS['username'], newobj.provenance.content.harvest_event.agent_id)
        self.assertTrue((newobj.uriref, relsext.isMemberOfCollection, self.coll)  in newobj.rels_ext.content)
        #check dc identifiers
        identifiers = newobj.dc.content.identifier_list
        self.assertTrue(newobj.pid in identifiers)
        self.assertTrue('PMC%s' % record.pmcid in identifiers)
        self.assertTrue(pmc_access_url(record.pmcid) in identifiers)
        #check pubmed link
        response = self.client.get(reverse('publication:view', kwargs={'pid': newobj.pid}))
        self.assertContains(response, 'View on PubMed Central')
        self.assertContains(response, pmc_access_url(record.pmcid))

        # try to re-ingest same record - should fail
        response = self.client.post(ingest_url, {'pmcid': record.pmcid},
                                    HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        expected, got = 400, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for %s (record already ingested)' \
                % (expected, got, ingest_url))
        self.assertContains(response, 'Record cannot be ingested',
                            status_code=expected)

        # set record to ignored - should also fail
        record.status = 'ignored'
        record.save()
        response = self.client.post(ingest_url, {'pmcid': record.pmcid},
                                    HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        expected, got = 400, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for %s (record with status "ignored")' \
                % (expected, got, ingest_url))
        self.assertContains(response, 'Record cannot be ingested',
                            status_code=expected)

        # try to ingest as user without required permissions
        record.status = 'harvested'	# reset record to allow ingest
        record.save()
        noperms_pwd = User.objects.make_random_password()
        noperms = User.objects.create_user('noperms_user', 'noperms@example.com', noperms_pwd)
        self.client.login(username=noperms.username, password=noperms_pwd)
        response = self.client.post(ingest_url,{'pmcid': record.pmcid},
                                    HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        expected, got = 403, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for %s (logged in but not a site admin)' \
                % (expected, got, ingest_url))


    def test_pdf(self):
        pdf_url = reverse('publication:pdf', kwargs={'pid': 'bogus:not-a-real-pid'})

        baseline_downloads = self.article.statistics().num_downloads

        response = self.client.get(pdf_url)
        expected, got = 404, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for %s (non-existent pid)' \
                % (expected, got, pdf_url))

        pdf_url = reverse('publication:pdf', kwargs={'pid': self.article.pid})
        response = self.client.get(pdf_url)
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for %s' \
                % (expected, got, pdf_url))
        updated_downloads = self.article.statistics().num_downloads
        self.assertEqual(updated_downloads, baseline_downloads + 1)


        # log'd in regular user  same result
        baseline_downloads = self.article.statistics().num_downloads
        self.client.login(**USER_CREDENTIALS['jmercy'])
        pdf_url = reverse('publication:pdf', kwargs={'pid': self.article.pid})
        response = self.client.get(pdf_url)
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for %s' \
                % (expected, got, pdf_url))
        updated_downloads = self.article.statistics().num_downloads
        self.assertEqual(updated_downloads, baseline_downloads + 1)
        self.client.logout()

        # log'd in admin user should not increase downoad count
        baseline_downloads = self.article.statistics().num_downloads
        self.client.login(**USER_CREDENTIALS['admin'])
        pdf_url = reverse('publication:pdf', kwargs={'pid': self.article.pid})
        response = self.client.get(pdf_url)
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for %s' \
                % (expected, got, pdf_url))
        updated_downloads = self.article.statistics().num_downloads
        self.assertEqual(updated_downloads, baseline_downloads)
        self.client.logout()




        # only check custom logic implemented here
        # (not testing eulfedora.views.raw_datastream logic)
        content_disposition = response['Content-Disposition']
        self.assert_(content_disposition.startswith('attachment; '),
                     'content disposition should be set to attachment, to prompt download')
        # PRELIMINARY download filename.....
        self.assert_(content_disposition.endswith('%s.pdf' % self.article.pid),
                     'content disposition filename should be a .pdf based on object pid')
        # last-modified - pdf or mods
        # FIXME: not applicable since we are adding access date to cover?
        # self.assertEqual(response['Last-Modified'],
        #                  str(self.article.pdf.created),
        #                  'last-modified should be pdf datastream modification time')

        # check that content has cover page
        with open(pdf_filename) as pdf:
            orig_pdf = PdfFileReader(pdf)
            orig_pdf_numpages = orig_pdf.numPages

        dl_pdf = PdfFileReader(StringIO(response.content))
        self.assertEqual(orig_pdf_numpages + 1, dl_pdf.numPages,
            'downloaded pdf should have 1 page more than original (+ cover page)')

        # modify mods - last-modified should change
        self.article.descMetadata.content.resource_type = 'text'
        self.article.save()
        response = self.client.get(pdf_url)
        # access latest version of article to compare
        a = self.repo.get_object(self.article.pid, type=Article)
        # last-modified - should be mods because it is newer than pdf
        # self.assertEqual(response['Last-Modified'],
        #                  str(a.descMetadata.created),
        #                  'last-modified should be newer of mods or pdf datastream modification time')

        # pdf error
        with patch.object(Article, 'pdf_with_cover') as mockpdfcover:
            # pyPdf error reading the pdf
            mockpdfcover.side_effect = PdfReadError
            response = self.client.get(pdf_url)
            dl_pdf = PdfFileReader(StringIO(response.content))
            self.assertEqual(orig_pdf_numpages, dl_pdf.numPages,
                'pdf download should fall back to original when adding cover page errors')

            # fedora error
            # create mockrequest to init RequestFailed
            mockrequest = Mock()
            mockrequest.status = 401
            mockrequest.reason = 'permission denied'
            mockpdfcover.side_effect = RequestFailed(mockrequest)
            response = self.client.get(pdf_url)
            expected, got = 404, response.status_code
            self.assertEqual(expected, got,
                'Expected %s but returned %s for %s (fedora error reading/merging pdf)' \
                             % (expected, got, pdf_url))

        # check embargoed article permissions
        embargo_end = datetime.datetime.now() + datetime.timedelta(days=1)
        embargo_end = embargo_end.strftime("%Y-%m-%d")
        self.article.descMetadata.content.embargo_end = embargo_end
        self.article.save()

        # not logged in
        pdf_url = reverse('publication:pdf', kwargs={'pid': self.article.pid})
        response = self.client.get(pdf_url)
        expected, got = 401, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for %s (embargoed article, anonymous user)' \
                % (expected, got, pdf_url))

        # logged in and owns the article
        self.client.login(**TESTUSER_CREDENTIALS)
        pdf_url = reverse('publication:pdf', kwargs={'pid': self.article.pid})
        response = self.client.get(pdf_url)
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for %s (embargoed article, logged in author)' \
                % (expected, got, pdf_url))

        # logged in but does not own the article
        self.article.owner = ""  # remove user from owner list
        self.article.save()

        pdf_url = reverse('publication:pdf', kwargs={'pid': self.article.pid})
        response = self.client.get(pdf_url)
        expected, got = 403, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for %s (embargoed article, logged in but not author)' \
                % (expected, got, pdf_url))

        # logged in and has the view_embargoed perm
        #Add view_embargoed perm to test user
        testuser = User.objects.get(username=TESTUSER_CREDENTIALS['username'])
        testuser.user_permissions.add(Permission.objects.get(codename='view_embargoed'))
        testuser.save()

        pdf_url = reverse('publication:pdf', kwargs={'pid': self.article.pid})
        response = self.client.get(pdf_url)
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for %s (embargoed article, logged in with view_embargoed permission)' \
                % (expected, got, pdf_url))


        # non-GET request should not increment view count
        baseline_dls = self.article.statistics().num_downloads
        response = self.client.head(pdf_url)
        updated_dls = self.article.statistics().num_downloads
        self.assertEqual(updated_dls, baseline_dls,
             'download count should not be incremented on non-GET request')


    def test_author_agreement(self):
        ds_url = reverse('publication:private_ds',
                kwargs={'pid': 'bogus:not-a-real-pid', 'dsid': 'authorAgreement'})
        response = self.client.get(ds_url)
        expected, got = 401, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for %s (not logged in, nonexistant pid)' \
                % (expected, got, ds_url))

        # user logged in and owns the article, but no author agreement
        self.client.login(**TESTUSER_CREDENTIALS)
        ds_url = reverse('publication:private_ds',
                kwargs={'pid': self.article.pid, 'dsid': 'authorAgreement'})
        response = self.client.get(ds_url)
        expected, got = 404, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for %s (article owner, no agreement)' \
                % (expected, got, ds_url))

        # add author agreement
        with open(pdf_filename_2) as author_agreement:
            self.article.authorAgreement.content = author_agreement
            self.article.save()

        # user logged in and owns the article, with author agreement
        response = self.client.get(ds_url)
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for %s' \
                % (expected, got, ds_url))

        # user logged in but does not own the article
        self.article.owner = ""  #remove user from owner list
        self.article.save()

        response = self.client.get(ds_url)
        expected, got = 403, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for %s (non-owner)' \
                % (expected, got, ds_url))


    @patch('openemory.publication.views.raw_audit_trail')
    def test_audit_trail(self, mockauditview):
        # actual audit trail view functionality is tested in eulfedora
        mockauditview.return_value = HttpResponse()

        audit_url = reverse('publication:audit-trail',
                kwargs={'pid': self.article.pid})

        response = self.client.get(audit_url)
        expected, got = 401, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for %s (not logged in)' \
                % (expected, got, audit_url))

        # normal user logged in - still no perms
        self.client.login(**TESTUSER_CREDENTIALS)
        response = self.client.get(audit_url)
        expected, got = 403, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for %s (logged in but not admin)' \
                % (expected, got, audit_url))

        # give testuser admin metadata perm
        # - Add view_admin_metadata perm
        testuser = User.objects.get(username=TESTUSER_CREDENTIALS['username'])
        testuser.groups.add(Group.objects.get(name='Site Admin'))
        testuser.user_permissions.add(Permission.objects.get(codename='view_admin_metadata'))
        testuser.save()

        response = self.client.get(audit_url)
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for %s (logged in as admin)' \
                % (expected, got, audit_url))


    @patch('openemory.publication.forms.EmoryLDAPBackend')
    @patch('openemory.publication.forms.marc_language_codelist')
    def test_edit_metadata(self, mocklangcodes, mockldap):
        # FIXME: this test is getting *way* too long and complicated.
        mocklangcodes.return_value =  xmlmap.load_xmlobject_from_file(lang_codelist_file,
                                                                      CodeList)

        self.client.post(reverse('accounts:login'), TESTUSER_CREDENTIALS) # login

        # non-existent pid should 404
        edit_url = reverse('publication:edit', kwargs={'pid': "fake-pid:1"})
        response = self.client.get(edit_url)
        expected, got = 404, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for %s (non-existent pid)' \
                % (expected, got, edit_url))

        # real object but NOT owned by the user
        admin_art = self.admin_repo.get_object(self.article.pid, type=Article)
        admin_art.owner = 'somebodyElse'
        admin_art.save()
        try:
            edit_url = reverse('publication:edit', kwargs={'pid': self.article.pid})
            response = self.client.get(edit_url)
            expected, got = 403, response.status_code
            self.assertEqual(expected, got,
                'Expected %s but returned %s for %s (real pid, wrong owner)' \
                    % (expected, got, edit_url))
        finally:
            admin_art.owner = TESTUSER_CREDENTIALS['username']
            admin_art.save()

        # real object owned by the current user
        self.article = self.repo.get_object(pid=self.article.pid, type=Article)
        # add author with no id to check optional read-only fields
        self.article.descMetadata.content.authors.append(
            AuthorName(family_name='Manhunter', given_name='Martian',
                                          affiliation='Mars Polytechnic Institute'))
        self.article.save()

        edit_url = reverse('publication:edit', kwargs={'pid': self.article.pid})
        response = self.client.get(edit_url)
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for %s (non-existent pid)' \
                % (expected, got, edit_url))
        self.assert_(isinstance(response.context['form'], ArticleModsEditForm),
                     'ArticleModsEditForm form should be set in response context on GET')

        # mods data should be pre-populated on the form
        self.assertContains(response, self.article.descMetadata.content.title_info.title)
        self.assertContains(response, self.article.descMetadata.content.abstract.text)
        self.assertContains(response, self.article.descMetadata.content.journal.publisher)

        # english should be default language value
        self.assertEqual('eng', response.context['form']['language_code'].value())

        # first author (which has empty netid) should be editable
        form_ctx = response.context['form']
        author_form = form_ctx.formsets['authors'][0]
        self.assertTrue(author_form.fields['affiliation'].widget.editable(),
                        'author widget with empty netid should allow affiliation editing.')

        # author does not have withdraw/reinstate
        self.assertNotContains(response, 'id_withdraw',
                msg_prefix='edit page should not contain withdraw option for authors')
        self.assertNotContains(response, 'id_withdraw_reason',
                msg_prefix='edit page should not contain withdraw reason for authors')
        self.assertNotContains(response, 'id_reinstate',
                msg_prefix='edit page should not contain reinstate option for authors')
        self.assertNotContains(response, 'id_reinstate_reason',
                msg_prefix='edit page should not contain reinstate reason for authors')

        # auto-complete urls should be set in javascript
        for facet in ['funder', 'journal_title', 'journal_publisher',
                      'keyword', 'author_affiliation']:
            self.assertContains(response, reverse('publication:suggest',
                                              kwargs={'field': facet}),
                msg_prefix='edit page should contain auto-suggest url for %s' % facet)

        self.assertNotContains(response, 'Featured:',
            msg_prefix='should not include mark as Featured input')

        # article mods form data - required fields only
        MODS_FORM_DATA = {
            'title_info-title': 'Capitalism and the Origins of the Humanitarian Sensibility',
            'title_info-subtitle': '',
            'title_info-part_name': '',
            'title_info-part_number': '',
            'authors-INITIAL_FORMS': '0',
            'authors-TOTAL_FORMS': '1',
            'authors-MAX_NUM_FORMS': '',
            'authors-0-id': '',
            'authors-0-family_name': '',
            'authors-0-given_name': '',
            'authors-0-affiliation': '',
            'funders-INITIAL_FORMS': '0',
            'funders-TOTAL_FORMS': '1',
            'funders-MAX_NUM_FORMS': '',
            'funders-0-name': '',
            'journal-title': 'The American Historical Review',
            'journal-issn': '',
            'journal-publisher': 'American Historical Association',
            'journal-volume-number': '',
            'journal-number-number': '',
            'abstract-text': '',
            'keywords-MAX_NUM_FORMS': '',
            'keywords-INITIAL_FORMS': '0',
            'keywords-TOTAL_FORMS': '1',
            'keywords-0-topic': '',
            'author_notes-MAX_NUM_FORMS': '',
            'author_notes-INITIAL_FORMS': '0',
            'author_notes-TOTAL_FORMS': '1',
            'author_notes-0-text': '',
            'version': 'Preprint: Prior to Peer Review',
            'publication_date_year': '2005',
            'publication_date_month': '01',
            'locations-MAX_NUM_FORMS': '',
            'locations-INITIAL_FORMS': '0',
            'locations-TOTAL_FORMS': '1',
            'locations-0-url': '',
            'language_code': 'eng',
            'subjects-MAX_NUM_FORMS': '',
            'subjects-INITIAL_FORMS': '0',
            'subjects-TOTAL_FORMS': '1',
            'subjects-0-id': 'id0729',
            'subjects-0-topic': 'Cinema',
            'subjects-1-id': 'id0377',
            'subjects-1-topic': '#0377',
            'supplemental_materials-MAX_NUM_FORMS': '',
            'supplemental_materials-INITIAL_FORMS': '0',
            'supplemental_materials-TOTAL_FORMS': '1',
            'supplemental_materials-0-url': '',
        }

        # invalid form - missing required field
        data = MODS_FORM_DATA.copy()
        data['title_info-title'] = ''
        # final version url/doi validation
        data['final_version-url'] = 'http://localhost/not/a/real/link'
        data['final_version-doi'] = 'doi:11.34/not/a/valid/doi'
        response = self.client.post(edit_url, data)
        self.assertContains(response, "field is required",
             msg_prefix='form displays required message when required Title field is empty')
        self.assertContains(response, "Enter a valid value",
             msg_prefix='form displays an error when DOI does not match regex')

        # post minimum required fields as "save" (keep unpublished)
        data = MODS_FORM_DATA.copy()

        # empty out all non-required fields
        for f in ['journal-publisher', 'journal-title', 'version', 'publication_date_year',
                  'publication_date_month', 'language_code', 'subjects-0-id',
                  'subjects-0-topic', 'subjects-1-id', 'subjects-1-topic']:
            data[f] = ''


        #set save-record flag should cause additional fields to become optional
        data['save-record'] = True
        response = self.client.post(edit_url, data, follow=True)
        self.assert_('invalid_form' not in response.context,
                     'posted form data should not result in an invalid form')

        #return code from redirect
        expected, got = 303, response.redirect_chain[0][1]
        self.assertEqual(expected, got,
            'Should redirect to profile page on successful save; expected %s but returned %s for %s' \
                         % (expected, got, edit_url))
        #final return code
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
            'Should redisplay edit form on successful save; expected %s but returned %s for %s' \
                         % (expected, got, edit_url))

        # get newly updated version of the object to inspect
        self.article = self.repo.get_object(pid=self.article.pid, type=Article)
        self.assertEqual(data['title_info-title'],
                         self.article.descMetadata.content.title_info.title)
        # check article state for save (instead of publish)
        self.assertEqual('I', self.article.state,
                         'article state should be Inactive after save')
        # check to make sure no itemID is present in rels-ext
        self.assertTrue(self.itemID_relation not in self.article.rels_ext.content)

        # non-required, empty fields should not be present in xml
        self.assertEqual(None, self.article.descMetadata.content.version)
        self.assertEqual(None, self.article.descMetadata.content.language_code)
        self.assertEqual(None, self.article.descMetadata.content.abstract)
        self.assertEqual(None, self.article.descMetadata.content.journal)
        self.assertEqual(0, len(self.article.descMetadata.content.funders))
        self.assertEqual(0, len(self.article.descMetadata.content.author_notes))
        self.assertEqual(0, len(self.article.descMetadata.content.subjects))

        # check session message
        messages = [str(m) for m in response.context['messages']]
        self.assertEqual(messages[0], "Saved <strong>%s</strong>" % self.article.label)

        # post minimum required fields as "publish"
        data = MODS_FORM_DATA.copy()
        data['publish-record'] = True
        response = self.client.post(edit_url, data)
        expected, got = 303, response.status_code
        self.assertEqual(expected, got,
            'Should redirect on successful publish; expected %s but returned %s for %s' \
                             % (expected, got, edit_url))
        self.assertEqual('http://testserver' + reverse('publication:view',
                                 kwargs={'pid': self.article.pid}),
                         response['Location'],
             'should redirect to article detail view page after publish')
        # get newly updated version of the object to check state
        self.article = self.repo.get_object(pid=self.article.pid, type=Article)
        self.assertEqual('A', self.article.state,
                         'article state should be Active after publish')
        # published record should have itemID in rels-ext
        self.assertTrue(self.itemID_relation in self.article.rels_ext.content)

        # make another request to check session message
        response = self.client.get(edit_url)
        messages = [str(m) for m in response.context['messages']]
        self.assertEqual(messages[0], "Published <strong>%s</strong>" % self.article.label)

        # post full metadata
        data = MODS_FORM_DATA.copy()
        with open(pdf_filename_2) as author_agreement:
            data.update({
                'title_info-subtitle': 'a critical approach',
                'title_info-part_name': 'Part 1',
                'title_info-part_number': 'The Beginning',
                'authors-0-id': TESTUSER_CREDENTIALS['username'],
                'authors-0-family_name': 'Tester',
                'authors-0-given_name': 'Sue',
                'authors-0-affiliation': 'Emory University',
                'funders-0-name': 'Mellon Foundation',
                'journal-volume-number': '90',
                'journal-number-number': '2',
                'journal-pages-start': '331',
                'journal-pages-end': '361',
                'abstract-text': 'An unprecedented wave of humanitarian reform sentiment swept through the societies of Western Europe, England, and North America in the hundred years following 1750.  Etc.',
                'keywords-0-topic': 'morality of capitalism',
                'author_notes-0-text': 'This paper was first given at the American Historical Association conference in 1943',
                'final_version-url': 'http://example.com/',
                'final_version-doi': 'doi:10.34/test/valid/doi',
                'locations-TOTAL_FORMS': '2',
                'locations-0-url': 'http://example.com/',
                'locations-1-url': 'http://google.com/',
                'publish-record': True,
                'subjects-0-id': 'id0900',
                'embargo_duration': '1 year',
                'author_agreement': author_agreement,
                'supplemental_materials-0-url': 'http://someurl.com',
            })
            response = self.client.post(edit_url, data)

        expected, got = 303, response.status_code
        self.assertEqual(expected, got,
            'Should redirect on successful update; expected %s but returned %s for %s' \
                             % (expected, got, edit_url))
        # get newly updated version of the object to inspect
        self.article = self.repo.get_object(pid=self.article.pid, type=Article)
        self.assertEqual(data['title_info-subtitle'],
                         self.article.descMetadata.content.title_info.subtitle)
        self.assertEqual(data['title_info-part_name'],
                         self.article.descMetadata.content.title_info.part_name)
        self.assertEqual(data['title_info-part_number'],
                         self.article.descMetadata.content.title_info.part_number)
        self.assertEqual(data['authors-0-id'],
                         self.article.descMetadata.content.authors[0].id)
        self.assertEqual(data['authors-0-family_name'],
                         self.article.descMetadata.content.authors[0].family_name)
        self.assertEqual(data['authors-0-given_name'],
                         self.article.descMetadata.content.authors[0].given_name)
        self.assertEqual(data['authors-0-affiliation'],
                         self.article.descMetadata.content.authors[0].affiliation)
        self.assertEqual(data['journal-volume-number'],
                         self.article.descMetadata.content.journal.volume.number)
        self.assertEqual(data['journal-number-number'],
                         self.article.descMetadata.content.journal.number.number)
        self.assertEqual(data['journal-pages-start'],
                         self.article.descMetadata.content.journal.pages.start)
        self.assertEqual(data['journal-pages-end'],
                         self.article.descMetadata.content.journal.pages.end)
        self.assertEqual(data['journal-pages-end'],
                         self.article.descMetadata.content.journal.pages.end)
        self.assertEqual(data['abstract-text'],
                         self.article.descMetadata.content.abstract.text)
        self.assertEqual(data['keywords-0-topic'],
                         self.article.descMetadata.content.keywords[0].topic)
        self.assertEqual(data['author_notes-0-text'],
                         self.article.descMetadata.content.author_notes[0].text)
        self.assertEqual(data['final_version-url'],
                         self.article.descMetadata.content.final_version.url)
        self.assertEqual(data['final_version-doi'],
                         self.article.descMetadata.content.final_version.doi)
        self.assertEqual(1, len(self.article.descMetadata.content.subjects))
        self.assertEqual(data['subjects-0-id'],
                         self.article.descMetadata.content.subjects[0].id)
        self.assertEqual('Cinema', self.article.descMetadata.content.subjects[0].topic)
        # embargo
        self.assertEqual(data['embargo_duration'],
                         self.article.descMetadata.content.embargo)
        #supplementa materials
        self.assertEqual(data['supplemental_materials-0-url'],
                         self.article.descMetadata.content.supplemental_materials[0].url)

        # author agreement
        self.assertTrue(self.article.authorAgreement.exists)
        self.assertEqual(pdf_md5sum_2, self.article.authorAgreement.checksum)

        # published record should have itemID in rels-ext
        self.assertTrue(self.itemID_relation in self.article.rels_ext.content)

        # save again with no embargo duration - embargo end date should be cleared
        data['embargo_duration'] = ''
        data['abstract-text'] = 'I came from a Windows machine \rso I have unnecessary control \rcharacters'
        del data['author_agreement']
        response = self.client.post(edit_url, data)
        self.article = self.repo.get_object(pid=self.article.pid, type=Article)
        self.assertEqual(None, self.article.descMetadata.content.embargo_end,
             'embargo end date should not be set on save+publish with no ' +
             'embargo duration (even if previously set)')

        expected = 'I came from a Windows machine so I have unnecessary control characters'
        # Should have removed \r characters
        self.assertEqual(expected, self.article.descMetadata.content.abstract.text)
        self.assertEqual(expected, self.article.dc.content.description)

        # edit as reviewer
        # - temporarily add testuser to admin group for review permissions
        testuser = User.objects.get(username=TESTUSER_CREDENTIALS['username'])
        testuser.groups.add(Group.objects.get(name='Site Admin'))
        testuser.save()
        response = self.client.get(edit_url)
        self.assertContains(response, 'Reviewed:',
            msg_prefix='admin edit form should include mark as reviewed input')
        self.assertContains(response, 'Featured:',
            msg_prefix='admin edit form should include mark as Featured input')

        # reviewer has withdraw option
        self.assertContains(response, 'id="id_withdraw"',
                msg_prefix='edit page should contain withdraw option for reviewers')
        self.assertContains(response, 'id="id_withdraw_reason"',
                msg_prefix='edit page should contain withdraw reason for reviewers')
        self.assertNotContains(response, 'id="id_reinstate"',
                msg_prefix='edit page should not contain reinstate option for reviewers')
        self.assertNotContains(response, 'id="id_reinstate_reason"',
                msg_prefix='edit page should not contain reinstate reason for reviewers')

        # post data as review - re-use complete data from last post
        del data['publish-record']
        data['reviewed'] = True   # mark as reviewed
        data['review-record'] = True # save via review
        data['rights_research_date'] = '2015-01-15'
        response = self.client.post(edit_url, data)
        expected, got = 303, response.status_code
        self.assertEqual(expected, got,
            'Should redirect on successful edit+review; expected %s but returned %s for %s' \
                             % (expected, got, edit_url))
        self.assertEqual('http://testserver' + reverse('publication:review-list'),
                         response['Location'],
             'should redirect to unreviewed list after admin review')

        article = self.repo.get_object(pid=self.article.pid, type=Article)
        self.assertTrue(article.provenance.exists)
        self.assertTrue(article.provenance.content.review_event)
        self.assertEqual(testuser.username,
                         article.provenance.content.review_event.agent_id)
        # make another request to check reviewed / session message
        response = self.client.get(edit_url)
        self.assertContains(response, article.provenance.content.review_event.detail)
        messages = [str(m) for m in response.context['messages']]
        self.assertEqual(messages[0], "Reviewed <strong>%s</strong>" % self.article.label)

        data['featured'] = True
        response = self.client.post(edit_url, data)
        self.assertTrue(FeaturedArticle.objects.filter(pid=self.article.pid),
                msg="pid should be in list of featured articles")

        #unpub item so you can't see featured checkbox
        self.article.state='I'
        self.article.save()
        response = self.client.get(edit_url)
        self.assertNotContains(response, 'Featured:',
            msg_prefix='should not see Featured input because article not publishe')

        # withdraw
        data['publish-record'] = True
        data['withdraw'] = True
        data['withdraw_reason'] = 'test reason abcd'
        response = self.client.post(edit_url, data)
        expected, got = 303, response.status_code
        self.assertEqual(expected, got,
            'Should redirect on withdraw; expected %s but returned %s for %s' \
                             % (expected, got, edit_url))
        article = self.repo.get_object(pid=self.article.pid, type=Article)
        self.assertEqual(article.state, 'I',
                         'Successful withdrawal should set article inactive.')

        provenance = article.provenance.content
        self.assertEqual(len(provenance.withdraw_events), 1,
                         'Successful withdrawal should add a withdraw event to provenance.')
        self.assertTrue(article.is_withdrawn)

        # after withdrawal, reinstate available to reviewers
        response = self.client.get(edit_url)
        self.assertNotContains(response, 'id="id_withdraw"',
                msg_prefix='edit page should not contain withdraw option for withdrawn article')
        self.assertNotContains(response, 'id="id_withdraw_reason"',
                msg_prefix='edit page should not contain withdraw reason for withdrawn article')
        self.assertContains(response, 'id="id_reinstate"',
                msg_prefix='edit page should contain reinstate option for withdrawn article')
        self.assertContains(response, 'id="id_reinstate_reason"',
                msg_prefix='edit page should contain reinstate reason for withdrawn article')

        # reinstate
        del data['withdraw']
        del data['withdraw_reason']
        data['reinstate'] = True
        data['reinstate_reason'] = 'test reason efgh'
        response = self.client.post(edit_url, data)
        expected, got = 303, response.status_code
        self.assertEqual(expected, got,
            'Should redirect on reinstate; expected %s but returned %s for %s' \
                             % (expected, got, edit_url))
        article = self.repo.get_object(pid=self.article.pid, type=Article)
        self.assertEqual(article.state, 'A',
                         'Successful reinstate should set article active.')
        # published record should have itemID in rels-ext
        self.assertTrue(self.itemID_relation in article.rels_ext.content)

        provenance = article.provenance.content
        self.assertEqual(len(provenance.withdraw_events), 1,
                         'Successful reinstate should retain withdraw event in provenance.')
        self.assertEqual(len(provenance.reinstate_events), 1,
                         'Successful reinstate should add withdraw event to provenance.')
        self.assertFalse(article.is_withdrawn)

        # second withdraw/reinstate
        del data['reinstate']
        del data['reinstate_reason']
        data['withdraw'] = True
        data['withdraw_reason'] = 'test reason ijkl'
        response = self.client.post(edit_url, data)
        article = self.repo.get_object(pid=self.article.pid, type=Article)
        provenance = article.provenance.content
        self.assertEqual(len(provenance.withdraw_events), 2,
                         'Second withdrawal should add withdraw event to provenance.')
        self.assertEqual(len(provenance.reinstate_events), 1,
                         'Second withdrawal should retain reinstate event in provenance.')
        self.assertTrue(article.is_withdrawn)

        del data['withdraw']
        del data['withdraw_reason']
        data['reinstate'] = True
        data['reinstate_reason'] = 'test reason mnop'
        response = self.client.post(edit_url, data)
        article = self.repo.get_object(pid=self.article.pid, type=Article)
        provenance = article.provenance.content
        self.assertEqual(len(provenance.withdraw_events), 2,
                         'Second reinstate should retain withdraw events in provenance.')
        self.assertEqual(len(provenance.reinstate_events), 2,
                         'Second reinstate should add reinstate event to provenance.')
        self.assertFalse(article.is_withdrawn)

    @patch('openemory.publication.views.solr_interface')
    def test_search_keyword(self, mock_solr_interface):
        mocksolr = MagicMock()	# required for __getitem__ / pagination
        mock_solr_interface.return_value = mocksolr
        mocksolr.query.return_value = mocksolr
        mocksolr.filter.return_value = mocksolr
        mocksolr.field_limit.return_value = mocksolr
        mocksolr.highlight.return_value = mocksolr
        mocksolr.sort_by.return_value = mocksolr
        mocksolr.facet_by.return_value = mocksolr
        mocksolr.count.return_value = 0	   # count required for pagination

        articles = MagicMock()
        mocksolr.execute.return_value = articles
        mocksolr.__getitem__.return_value = articles

        search_url = reverse('publication:search')
        response = self.client.get(search_url, {'keyword': 'cheese'})

        mocksolr.query.assert_any_call('cheese')
        mocksolr.filter.assert_any_call(content_model=Article.ARTICLE_CONTENT_MODEL,
                                           state='A')

        mocksolr.query.assert_any_call(name_text=['cheese'])
        mocksolr.filter.assert_any_call(record_type=EsdPerson.record_type)

        self.assert_(isinstance(response.context['results'], paginator.Page),
                     'paginated solr result should be set in response context')
        self.assertEqual(articles, response.context['results'].object_list)
        self.assertEqual(['cheese'], response.context['search_terms'])

        # no results found - should be indicated
        # (empty result because execute return value magicmock is currently empty)
        self.assertContains(response, 'Your search term did not match any articles')


    @patch('openemory.publication.views.solr_interface')
    def test_search_person(self, mock_solr_interface):
        mocksolr = MagicMock()	# required for __getitem__ / pagination
        mock_solr_interface.return_value = mocksolr
        mocksolr.query.return_value = mocksolr
        mocksolr.filter.return_value = mocksolr
        mocksolr.field_limit.return_value = mocksolr
        mocksolr.highlight.return_value = mocksolr
        mocksolr.sort_by.return_value = mocksolr
        mocksolr.facet_by.return_value = mocksolr
        mocksolr.count.return_value = 0	   # count required for pagination

        search_url = reverse('publication:search')
        response = self.client.get(search_url, {'keyword': '"Firstname Lastname"'})

        # article search
        expected = {'creator': 'Lastname, Firstname'}
        self.assertEqual(mocksolr.filter.call_args[1], expected)

        #person search
        expected = {'directory_name': 'Firstname Lastname'}
        self.assertEqual(mocksolr.query.call_args_list[2][1], expected)
        expected = {'first_name': 'Firstname', 'last_name': 'Lastname'}
        self.assertEqual(mocksolr.query.call_args_list[3][1], expected)

    @patch('openemory.publication.views.solr_interface')
    def test_search_phrase(self, mock_solr_interface):
        mocksolr = MagicMock()	# required for __getitem__ / pagination
        mock_solr_interface.return_value = mocksolr
        mocksolr.query.return_value = mocksolr
        mocksolr.filter.return_value = mocksolr
        mocksolr.field_limit.return_value = mocksolr
        mocksolr.highlight.return_value = mocksolr
        mocksolr.sort_by.return_value = mocksolr
        mocksolr.facet_by.return_value = mocksolr
        # count required for pagination; > 10 to test pagination
        mocksolr.count.return_value = 11

        articles = [
            {'pid': 'test:1',  'title': 'An Article', 'score': 0.3,
             'abstract': 'summary description of content' }
        ]
        mocksolr.execute.return_value = articles
        mocksolr.__getitem__.return_value = articles

        search_url = reverse('publication:search')
        response = self.client.get(search_url, {'keyword': 'cheese "sharp cheddar"'})

        mocksolr.query.assert_any_call('cheese', 'sharp cheddar')
        mocksolr.filter.assert_any_call(content_model=Article.ARTICLE_CONTENT_MODEL,
                                        state='A')

        mocksolr.query.assert_any_call(name_text=['cheese', 'sharp cheddar'])
        mocksolr.filter.assert_any_call(record_type=EsdPerson.record_type)

        self.assert_(isinstance(response.context['results'], paginator.Page),
                     'paginated solr result should be set in response context')
        self.assertEqual(articles, response.context['results'].object_list)
        self.assertEqual(response.context['search_terms'], ['cheese', 'sharp cheddar'])

        self.assertContains(response, '<div class="pages"',
            msg_prefix='pagination links should be present on search results page')

        # minimal testing for article content display
        self.assertContains(response, articles[0]['title'],
            msg_prefix='article title should be displayed')
        self.assertContains(response, reverse('publication:view', args=[articles[0]['pid']]),
            msg_prefix='article view url should be included in search page')
        # NOTE: relevance score not currently displayed in new 352media designls -
        #self.assertContains(response, articles[0]['score'],
        #    msg_prefix='article relevance score should be displayed when present')
        self.assertContains(response, articles[0]['abstract'],
            msg_prefix='article abstract should be displayed when present')


    @patch('openemory.publication.views.solr_interface')
    def test_search_within(self, mock_solr_interface):
        mocksolr = MagicMock()	# required for __getitem__ / pagination
        mock_solr_interface.return_value = mocksolr
        mocksolr.query.return_value = mocksolr
        mocksolr.filter.return_value = mocksolr
        mocksolr.field_limit.return_value = mocksolr
        mocksolr.highlight.return_value = mocksolr
        mocksolr.sort_by.return_value = mocksolr
        mocksolr.facet_by.return_value = mocksolr
        # count required for pagination; > 10 to test pagination links show up
        mocksolr.count.return_value = 11

        articles = MagicMock()
        mocksolr.execute.return_value = articles
        mocksolr.__getitem__.return_value = articles

        search_url = reverse('publication:search')
        response = self.client.get(search_url, {'keyword': 'cheese "sharp cheddar"',
                                                'within_keyword': 'discount', 'past_within_keyword': 'quality'})

        mocksolr.query.assert_any_call('cheese', 'sharp cheddar')
        mocksolr.filter.assert_any_call(state="A", content_model=Article.ARTICLE_CONTENT_MODEL)
        mocksolr.filter.assert_any_call('quality', 'discount')

        mocksolr.execute.assert_called_once()

        self.assert_(isinstance(response.context['results'], paginator.Page),
                     'paginated solr result should be set in response context')
        self.assertEqual(articles, response.context['results'].object_list)
        self.assertEqual(response.context['search_terms'], ['cheese', 'sharp cheddar', 'quality', 'discount'])

        self.assertContains(response, '<div class="pages"',
            msg_prefix='pagination links should be present on search results page')


    @patch('openemory.publication.views.solr_interface')
    def test_suggest(self, mock_solr_interface):
        mocksolr = mock_solr_interface.return_value
        mocksolr.query.return_value = mocksolr
        mocksolr.paginate.return_value = mocksolr
        mocksolr.facet_by.return_value = mocksolr
        # mock-up of what sunburnt returns for facets & counts
        mocksolr.execute.return_value.facet_counts.facet_fields = {
            'funder_facet': [
                ('Mellon Foundation', 3),
                ('MNF', 2)
                ]
        }
        funder_autocomplete_url = reverse('publication:suggest',
                                          kwargs={'field': 'funder'})
        response = self.client.get(funder_autocomplete_url, {'term': 'M'})
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for %s' % \
                         (expected, got, funder_autocomplete_url))
        # inspect return response
        self.assertEqual('application/json', response['Content-Type'],
             'should return json on success')
        # inspect solr query/facet options
        mocksolr.query.assert_called_once()
        mocksolr.paginate.assert_called_with(rows=0)
        mocksolr.facet_by.assert_called_with('funder_facet',
                                             prefix='M',
                                             sort='count',
                                             limit=15)
        mocksolr.execute.assert_called_once()
        # inspect the result
        data = json.loads(response.content)
        self.assertEqual('Mellon Foundation', data[0]['value'])
        self.assertEqual('Mellon Foundation (3)', data[0]['label'])
        self.assertEqual('MNF (2)', data[1]['label'])


    @patch('openemory.common.romeo.search_journal_title')
    def test_suggest_journal_title(self, mock_search):
        mock_search.return_value = [
                Mock(title='DNA (Mary Ann Liebert, Inc.)',
                     publisher_romeo='', issn='0198-0238'),
                Mock(title='DNA and Cell Biology',
                     publisher_romeo='Mary Ann Liebert', issn='1044-5498'),
                Mock(title='DNA Repair',
                     publisher_romeo='Elsevier', issn='1568-7864'),
                # 2 more in real results
            ]

        url = reverse('publication:suggest',
                      kwargs={'field': 'journal_title'})
        response = self.client.get(url, {'term': 'dna'})

        self.assertEqual(200, response.status_code)
        self.assertEqual('application/json', response['Content-Type'])
        mock_search.assert_called_once_with('dna', type='starts')

        data = json.loads(response.content)
        self.assertEqual(len(data), 3)
        self.assertEqual(data[0], {
                'label': 'DNA (Mary Ann Liebert, Inc.) (unknown publisher)',
                'value': 'DNA (Mary Ann Liebert, Inc.)',
                'issn': '0198-0238',
                'publisher': '',
            })
        self.assertEqual(data[1], {
                'label': 'DNA and Cell Biology (Mary Ann Liebert)',
                'value': 'DNA and Cell Biology',
                'issn': '1044-5498',
                'publisher': 'Mary Ann Liebert',
            })
        self.assertEqual(data[2], {
                'label': 'DNA Repair (Elsevier)',
                'value': 'DNA Repair',
                'issn': '1568-7864',
                'publisher': 'Elsevier',
            })

    maxDiff = None

    @patch('openemory.common.romeo.search_publisher_name')
    def test_suggest_journal_publisher(self, mock_search):
        # name is a normal arg for Mock, so create and *then* config:
        mock_search.return_value = [Mock(), Mock(), Mock()]
        mock_search.return_value[0].configure_mock(
                name='American Association for Cancer Research',
                alias='', id='1046',
                preprint_archiving='unclear',
                preprint_restrictions=[],
                postprint_archiving='restricted',
                postprint_restrictions=[
                    '<num>12</num> <period units="month">months</period> embargo'
                ],
                pdf_archiving='cannot',
                pdf_restrictions=[],
                )
        mock_search.return_value[1].configure_mock(
                name='Cancer Intelligence',
                alias='', id='992',
                preprint_archiving='unclear',
                preprint_restrictions=[],
                postprint_archiving='can',
                postprint_restrictions=[],
                pdf_archiving='unknown',
                pdf_restrictions=[],
                )
        mock_search.return_value[2].configure_mock(
                name='International Institute of Anticancer Research',
                alias='IIAR', id='359',
                preprint_archiving='unclear',
                preprint_restrictions=[],
                postprint_archiving='cannot',
                postprint_restrictions=[],
                pdf_archiving='unknown',
                pdf_restrictions=[],
                )
        # 2 more in real results

        url = reverse('publication:suggest',
                      kwargs={'field': 'journal_publisher'})
        response = self.client.get(url, {'term': 'cancer'})

        self.assertEqual(200, response.status_code)
        self.assertEqual('application/json', response['Content-Type'])
        mock_search.assert_called_once_with('cancer', versions='all')

        data = json.loads(response.content)
        self.assertEqual(len(data), 3)
        self.assertEqual(data[0], {
                'label': 'American Association for Cancer Research',
                'value': 'American Association for Cancer Research',
                'romeo_id': '1046',
                'preprint': {
                    'archiving': 'unclear',
                    'restrictions': [],
                },
                'postprint': {
                    'archiving': 'restricted',
                    'restrictions': [
                        '<num>12</num> <period units="month">months</period> embargo',
                    ],
                },
                'pdf': {
                    'archiving': 'cannot',
                    'restrictions': [],
                },
            })
        self.assertEqual(data[1], {
                'label': 'Cancer Intelligence',
                'value': 'Cancer Intelligence',
                'romeo_id': '992',
                'preprint': {
                    'archiving': 'unclear',
                    'restrictions': [],
                },
                'postprint': {
                    'archiving': 'can',
                    'restrictions': [],
                },
                'pdf': {
                    'archiving': 'unknown',
                    'restrictions': [],
                },
            })
        self.assertEqual(data[2], {
                'label': 'International Institute of Anticancer Research (IIAR)',
                'value': 'International Institute of Anticancer Research',
                'romeo_id': '359',
                'preprint': {
                    'archiving': 'unclear',
                    'restrictions': [],
                },
                'postprint': {
                    'archiving': 'cannot',
                    'restrictions': [],
                },
                'pdf': {
                    'archiving': 'unknown',
                    'restrictions': [],
                },
            })

    @patch('openemory.publication.views.solr_interface')
    def test_search_faceting(self, mock_solr_interface):
        mocksolr = MagicMock()	# required for __getitem__ / pagination
        mock_solr_interface.return_value = mocksolr
        mocksolr.query.return_value = mocksolr
        mocksolr.filter.return_value = mocksolr
        mocksolr.field_limit.return_value = mocksolr
        mocksolr.highlight.return_value = mocksolr
        mocksolr.sort_by.return_value = mocksolr
        mocksolr.facet_by.return_value = mocksolr
        mocksolr.paginate.return_value = mocksolr
        mocksolr.count.return_value = 1	   # count required for pagination

        articles = MagicMock()
        articles.facet_counts.facet_fields = {
            'researchfield_facet': [],
            'pubyear': [('2003', 1), ('2010', 25)],
            'creator_facet': [('Mouse, Minnie', 1),
                              ('McDuck, Scrooge', 100)],
            'journal_title_facet': [('Journal of Civil Rights Administration', 1)]

            }
        mocksolr.execute.return_value = articles
        mocksolr.__getitem__.return_value = articles

        search_url = reverse('publication:search')
        response = self.client.get(search_url, {'keyword': 'che*'})
        facet_fields = [args[0] for args, kwargs in mocksolr.facet_by.call_args_list]
        for solr_facet in ['pubyear', 'creator_facet', 'researchfield_facet',
                           'journal_title_facet']:
            self.assert_(solr_facet in facet_fields,
                         'solr query should request facets for "%s" field' % solr_facet)

        self.assert_('facets' in response.context,
                     'facets should be set in response context for display to user')
        # inspect display version of facets
        display_facets = response.context['facets']
        display_facet_args = [f['queryarg'] for f in display_facets]
        # should have human-readable display names
        self.assert_('author' in display_facet_args)
        self.assert_('journal' in display_facet_args)
        self.assert_('year' in display_facet_args)
        self.assert_('subject' not in display_facet_args,
                     'empty facet list should not be passed for display')


        # search with facets
        facet_opts = {'keyword': 'che*',
                      'author': ['Mouse, Minnie',
                                 'McDuck, Scrooge'],
                      'year': '2010'}
        response = self.client.get(search_url, facet_opts)
        display_facets = response.context['facets']
        display_facet_args = [f['queryarg'] for f in display_facets]
        display_facet_values = dict((f['queryarg'], f['values'])
                                    for f in display_facets)
        # check that filters currently in effect are not displayed as facets
        self.assert_('author' not in display_facet_args,
                     'active filters should not be displayed as facets')
        # year facet should be length 1 (without 2010)
        self.assertEqual(1, len(display_facet_values['year']))

        # active filters for display / removal
        self.assert_('active_filters' in response.context,
                     'active filters should be set in response context')
        active_filters = response.context['active_filters']
        active_filters_dict = dict(active_filters)
        # active_filters is a list of tuples:
        #   - first portion should be the filter value for display
        #   - second portion should be a url to *remove* only this filter
        # we've turned these into the key and value of active_filters_dict
        # for easier lookup. here we're checking that for each facet in
        # facet_opts above, the active_filters has an entry whose first part
        # (the dict key for active_filters_dict) is the value and whose
        # second part (the dict value) is a url that contains all of the
        # active_filters except that one.
        #
        # note that keyword args are not facets and thuse never get included
        # in active_filters as the first part (the dict key) and are always
        # present in the second part (the dict value).
        self.assert_(facet_opts['keyword'] not in active_filters_dict)

        self.assert_(facet_opts['author'][0] in active_filters_dict)
        self.assert_(urlencode({'keyword': 'che*'})
                     in active_filters_dict[facet_opts['author'][0]])
        self.assert_(urlencode({'author': 'Mouse, Minnie'})
                     not in active_filters_dict[facet_opts['author'][0]])
        self.assert_(urlencode({'author': 'McDuck, Scrooge'})
                     in active_filters_dict[facet_opts['author'][0]])
        self.assert_(urlencode({'year': '2010'})
                     in active_filters_dict[facet_opts['author'][0]])

        self.assert_(facet_opts['author'][1] in active_filters_dict)
        self.assert_(urlencode({'keyword': 'che*'})
                     in active_filters_dict[facet_opts['author'][1]])
        self.assert_(urlencode({'author': 'Mouse, Minnie'})
                     in active_filters_dict[facet_opts['author'][1]])
        self.assert_(urlencode({'author': 'McDuck, Scrooge'})
                     not in active_filters_dict[facet_opts['author'][1]])
        self.assert_(urlencode({'year': '2010'})
                     in active_filters_dict[facet_opts['author'][0]])

        self.assert_(facet_opts['year'] in active_filters_dict)
        self.assert_(urlencode({'keyword': 'che*'})
                     in active_filters_dict[facet_opts['year']])
        self.assert_(urlencode({'author': 'Mouse, Minnie'})
                     in active_filters_dict[facet_opts['year']])
        self.assert_(urlencode({'author': 'McDuck, Scrooge'})
                     in active_filters_dict[facet_opts['year']])
        self.assert_(urlencode({'year': '2010'})
                     not in active_filters_dict[facet_opts['year']])

    def test_view_article(self):
        #Add harvest and review events to article
        mockuser = Mock()
        mockuser.get_profile.return_value.get_full_name.return_value = "Joe User"
        mockuser.username = 'juser'

        self.article.provenance.content.init_object(self.article.pid, 'pid')
        self.article.provenance.content.harvested(mockuser, 'pmc123')
        self.article.provenance.content.reviewed(mockuser)
        self.article.save()

        view_url = reverse('publication:view', kwargs={'pid': self.article.pid})

        baseline_views = self.article.statistics().num_views

        # view minimal test record
        response = self.client.get(view_url)
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for %s' % \
                         (expected, got, view_url))
        self.assertContains(response, self.article.pid)
        self.assertContains(response, self.article.descMetadata.content.title_info.title)
        self.assertContains(response, unicode(self.article.descMetadata.content.abstract))
        self.assertContains(response, self.article.descMetadata.content.journal.publisher)
        self.assertContains(response, reverse('publication:pdf', kwargs={'pid': self.article.pid}))
        self.assertContains(response, "(%s)" % filesizeformat(self.article.pdf.size))
        updated_views = self.article.statistics().num_views
        self.assertEqual(updated_views, baseline_views + 1)
        views_text = '''"itemStats">%s View<''' % (updated_views,)
        downloads_text = '''"itemStats">'''
        harvest_text = "Harvested pmc123 from PubMed Central by Joe User"
        review_text = "Reviewed by Joe User"
        self.assertContains(response, views_text)
        self.assertContains(response, downloads_text)
        # only site admin should can view provenance
        self.assertNotContains(response, harvest_text)
        self.assertNotContains(response, review_text)

        # incomplete record should not display 'None' for empty values
        # FIXME: this fails in 1.1.x. not sure why yet, but it's not enough
        # to hold up release.
        #self.assertNotContains(response, 'None')

        # populate record with full metadata
        amods = self.article.descMetadata.content
        #amods.title_info.subtitle = 'the Current Situation'
        amods.title_info.part_number = 'Part 1'
        amods.title_info.part_name = 'Where we are now'
        amods.authors.extend([AuthorName(family_name='Mouse', given_name='Minnie', id='mmouse',
                                          affiliation='Emory University'),
                              AuthorName(family_name='Science', given_name='Joe',
                                         affiliation='GA Tech'),])
        amods.funders.extend([FundingGroup(name='NSF'), FundingGroup(name='CDC')])
        amods.create_journal()
        amods.journal.title = 'Nature'
        amods.journal.publisher = 'Nature Publishing Group'
        amods.journal.create_volume()
        amods.journal.volume.number = 92
        amods.journal.create_number()
        amods.journal.number.number = 3
        amods.journal.create_pages()
        amods.journal.pages.start = 362
        amods.journal.pages.end = 376
        amods.publication_date = 2009
        amods.genre = 'Article'
        amods.version = 'Preprint: Prior to Peer Review'
        amods.create_final_version()
        amods.final_version.url = 'http://www.jstor.org/stable/1852669'
        amods.final_version.doi = 'doi:10/1073/pnas/1111088108'
        amods.author_notes.append(AuthorNote(text='published under a different name'))
        amods.keywords.extend([Keyword(topic='nature'),
                                Keyword(topic='biomedical things')])
        amods.subjects.append(ResearchField(topic='Mathematics', id='id0405'))
        amods.create_admin_note()
        amods.admin_note.text = 'The admin note'
        amods.rights_research_date = '2011-011-11'
        amods.supplemental_materials.append(SupplementalMaterial(url='http://interestingsupportingmaterial.com'))
        self.article.save()


        # log'd in usser incriiments view count
        baseline_views = self.article.statistics().num_views
        self.client.login(**USER_CREDENTIALS['jmercy'])
        response = self.client.get(view_url)
        self.assertEquals(self.article.statistics().num_views, baseline_views+1)
        self.client.logout()

        # admin does not incriment view count
        baseline_views = self.article.statistics().num_views
        self.client.login(**USER_CREDENTIALS['admin'])
        response = self.client.get(view_url)
        self.assertEquals(self.article.statistics().num_views, baseline_views)
        self.client.logout()

        response = self.client.get(view_url)
        # full title, with subtitle & parts
        self.assertContains(response, '%s' % amods.title_info.title)
        # author names, affiliations, links
        self.assertContains(response, amods.authors[0].family_name)
        self.assertContains(response, amods.authors[0].given_name)
        self.assertContains(response, amods.authors[0].affiliation)
        self.assertContains(response, reverse('accounts:profile',
                                              kwargs={'username': amods.authors[0].id}))
        self.assertContains(response, amods.authors[1].family_name)
        self.assertContains(response, amods.authors[1].given_name)
        self.assertContains(response, amods.authors[1].affiliation)
        # article links/versions
        self.assertContains(response, 'Final Published Version')
        self.assertContains(response, amods.final_version.url)
        self.assertContains(response, amods.final_version.doi)
        # journal/publication info
        self.assertContains(response, amods.journal.title)
        self.assertContains(response, 'Volume %s' % amods.journal.volume.number)
        self.assertContains(response, 'Number %s' % amods.journal.number.number)
        self.assertContains(response, amods.publication_date)
        self.assertContains(response, 'Pages %s-%s' % (amods.journal.pages.start, amods.journal.pages.end))
        self.assertContains(response, amods.genre)
        self.assertContains(response, amods.version)
        self.assertContains(response, 'Author Notes')
        self.assertContains(response, amods.author_notes[0].text)
        # subjects & keywords
        self.assertContains(response, amods.subjects[0].topic)
        self.assertContains(response, amods.keywords[0].topic)
        self.assertContains(response, amods.keywords[1].topic)
        # funders
        self.assertContains(response, 'Research Funded in Part By')
        self.assertContains(response, amods.funders[0].name)
        self.assertContains(response, amods.funders[1].name)
        #supplemental materials
        self.assertContains(response, amods.supplemental_materials[0].url)

        # embargoed record
        nextyear = date.today() + relativedelta(years=1)
        amods.embargo_end = nextyear.isoformat()
        self.article.save()
        response = self.client.get(view_url)
        self.assertNotContains(response,
                               reverse('publication:pdf', kwargs={'pid': self.article.pid}),
            msg_prefix='guest should not see PDF link for embargoed record')
        self.assertContains(response,
                            'PDF restricted until %s' % amods.embargo_end,
            msg_prefix='guest should see PDF access restricted text when article is embargoed')

        self.assertNotContains(response, "(%s)" % filesizeformat(self.article.pdf.size),
                               msg_prefix='Should not see the file size')


        # admin should see edit link
        # - temporarily add testuser to admin group for review permissions
        # - Add view_admin_metadata perm
        testuser = User.objects.get(username=TESTUSER_CREDENTIALS['username'])
        testuser.groups.add(Group.objects.get(name='Site Admin'))
        testuser.user_permissions.add(Permission.objects.get(codename='view_admin_metadata'))
        testuser.save()
        self.client.login(**TESTUSER_CREDENTIALS)
        response = self.client.get(view_url)
        self.assertContains(response, reverse('publication:edit',
                                              kwargs={'pid': self.article.pid}),
            msg_prefix='site admin should see article edit link on detail view page')
        self.assertContains(response,
                            'PDF restricted until %s' % amods.embargo_end,
            msg_prefix='admin should see PDF access restricted text when article is embargoed')
        self.assertContains(response,
                               reverse('publication:pdf', kwargs={'pid': self.article.pid}),
            msg_prefix='admin should see PDF link even for embargoed record')
        self.assertContains(response, "(%s)" % filesizeformat(self.article.pdf.size),
                            msg_prefix = "Admin should see filesize even though it is embargoed")

        # site admin can see all premis events
        self.assertContains(response, harvest_text)
        self.assertContains(response, review_text)

        self.assertContains(response, reverse('publication:audit-trail',
                                              kwargs={'pid': self.article.pid}),
            msg_prefix='admin should see link to audit trail')

        self.assertContains(response, 'Admin Note',
            msg_prefix='admin should see Admin Note section')

        self.assertContains(response, amods.admin_note.text,
            msg_prefix='admin should see the Admin Note value')
        # non-GET request should not increment view count
        baseline_views = self.article.statistics().num_views
        response = self.client.head(view_url)
        updated_views = self.article.statistics().num_views
        self.assertEqual(updated_views, baseline_views,
             'view count should not be incremented on non-GET request')

    def test_view_article_license(self):
        view_url = reverse('publication:view', kwargs={'pid': self.article.pid})
        response = self.client.get(view_url)
        self.assertNotContains(response, 'Copyright information',
            msg_prefix='record with no NLM permissions does not display copyright info')

        # populate record with nlm license information
        nlm = self.article.contentMetadata.content
        nlm.copyright = '(c) 2010 by ADA.'
        nlm.license = xmlmap.load_xmlobject_from_string(NlmLicenseTest.LICENSE_FIXTURES['embedded_link'],
                                                        xmlclass=NlmLicense)
        mods = self.article.descMetadata.content
        mods.create_license()
        mods.license.link = nlm.license.link
        mods.license.text = nlm.license.text
        mods.create_copyright()
        mods.copyright.text = nlm.copyright

        self.article.save()
        response = self.client.get(view_url)
        self.assertContains(response, 'Copyright information',
            msg_prefix='record with NLM copyright info & license displays copyright info')
        self.assertContains(response, mods.copyright.text,
            msg_prefix='NLM copyright statement should be displayed as-is')
        # next two statements test parts of the license b/c text version has different whiespace than html version
        self.assertContains(response, "Readers may use this",
            msg_prefix='text version of MODS license should be displayed')
        self.assertContains(response, '<a href="http://creativecommons.org/licenses/by-nc-nd/3.0/" rel="nofollow">http://creativecommons.org/licenses/by-nc-nd/3.0/</a>',
            msg_prefix='text version of MODS license should be displayed')
        self.assertContains(response, '/images/cc/%s.png' % mods.license.cc_type,
            msg_prefix='Creative Commons icon should be displayed for CC license')

    def test_view_article_biblio(self):
        # augment our article with some interesting biblio metadata
        amods = self.article.descMetadata.content
        amods.title_info.subtitle = 'A love story'
        amods.authors.append(AuthorName(family_name='Mouse', given_name='Mickey'))
        amods.authors.append(AuthorName(family_name='Mouse', given_name='Minnie'))
        amods.journal.title = 'Journal of Important Things'
        amods.journal.create_volume()
        amods.journal.volume.number = '11'
        amods.journal.create_number()
        amods.journal.number.number = '5'
        amods.journal.create_pages()
        amods.journal.pages.start = '1742'
        amods.journal.pages.end = '2637'
        amods.publication_date = '2011-08-24'
        amods.keywords.append(Keyword(geographic='Atlanta'))
        amods.keywords.append(Keyword(name=mods.Name(name_parts=[mods.NamePart(text='William'),
                                                                 mods.NamePart(text='Shakespeare')])))
        amods.keywords.append(Keyword(topic='rumba'))
        amods.keywords.append(Keyword(title='Divine Comedy, The'))
        amods.create_final_version()
        amods.final_version.doi = 'doi:42.1234/1-2-3-4'
        amods.language = 'English'
        self.article.save()

        view_url = reverse('publication:biblio-data', kwargs={'pid': self.article.pid})
        response = self.client.get(view_url)

        self.assertContains(response, 'Provider: ')
        self.assertContains(response, 'Content: ')
        self.assertContains(response, '\r\n\r\nTY  - JOUR\r\n')
        self.assertContains(response, 'TI  - A very scholarly article\r\n')
        self.assertContains(response, 'T2  - A love story\r\n')
        self.assertContains(response, 'AU  - Mouse, Mickey\r\n')
        self.assertContains(response, 'AU  - Mouse, Minnie\r\n')
        self.assertContains(response, 'JO  - Journal of Important Things\r\n')
        self.assertContains(response, 'PB  - Big Deal Publications\r\n')
        self.assertContains(response, 'VL  - 11\r\n')
        self.assertContains(response, 'IS  - 5\r\n')
        self.assertContains(response, 'SP  - 1742\r\n')
        self.assertContains(response, 'EP  - 2637\r\n')
        self.assertContains(response, 'PY  - 2011\r\n')
        self.assertContains(response, 'DA  - 2011-08-24\r\n')
        self.assertContains(response, 'KW  - Atlanta\r\n')
        self.assertContains(response, 'KW  - William Shakespeare\r\n')
        self.assertContains(response, 'KW  - rumba\r\n')
        self.assertContains(response, 'KW  - Divine Comedy, The\r\n')
        self.assertContains(response, 'DO  - doi:42.1234/1-2-3-4\r\n')
        self.assertContains(response, 'LA  - English\r\n')
        self.assertContains(response, 'ER  - \r\n')


    @patch('openemory.publication.views.solr_interface')
    def test_review_list(self, mock_solr_interface):
        review_url = reverse('publication:review-list')
        mocksolr = MagicMock()	# required for __getitem__ / pagination
        mock_solr_interface.return_value = mocksolr
        mocksolr.query.return_value = mocksolr
        mocksolr.filter.return_value = mocksolr
        mocksolr.sort_by.return_value = mocksolr
        mocksolr.exclude.return_value = mocksolr
        mocksolr.field_limit.return_value = mocksolr
        mocksolr.count.return_value = 1	   # count required for pagination
        rval = [{'pid': 'test:1'}]
        mocksolr.__getitem__.return_value = rval
        mocksolr.execute.return_value = rval

        # not logged in
        response = self.client.get(review_url)
        expected, got = 401, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for %s as anonymous user' % \
                         (expected, got, review_url))

        # login as staff
        self.client.post(reverse('accounts:login'), USER_CREDENTIALS['faculty'])
        response = self.client.get(review_url)
        expected, got = 403, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for %s as staff user' % \
                         (expected, got, review_url))

        # login as admin
        self.client.post(reverse('accounts:login'), USER_CREDENTIALS['admin'])
        response = self.client.get(review_url)
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for %s as site admin' % \
                         (expected, got, review_url))

        self.assert_(isinstance(response.context['results'], paginator.Page),
                     'paginated solr result should be set in response context')

        self.assertEqual(rval, response.context['results'].object_list,
                         'solr result should be accessible in response context')

        self.assertContains(response, reverse('publication:edit',
                                              kwargs={'pid': 'test:1'}),
             msg_prefix='site admin should see edit link for unreviewed articles')
        self.assertContains(response, 'Article 1 of 1',
             msg_prefix='page should include total number of articles')


        # check solr query args
        mocksolr.query.assert_called()
        # should exclude records with any review date set
        mocksolr.exclude.assert_called_with(review_date__any=True)
        # should filter on content model & active (published) records
        mocksolr.filter.assert_called_with(content_model=Article.ARTICLE_CONTENT_MODEL,
                                           state='A')
        qargs, kwargs = mocksolr.sort_by.call_args
        self.assertEqual('created', qargs[0],
                         'solr results should be sort by record creation date')
        mocksolr.field_limit.assert_called()

    @patch('openemory.publication.views.solr_interface')
    def test_review_list_ajax(self, mock_solr_interface):
        review_url = reverse('publication:review-list')
        mocksolr = MagicMock()	# required for __getitem__ / pagination
        mock_solr_interface.return_value = mocksolr
        mocksolr.query.return_value = mocksolr
        mocksolr.filter.return_value = mocksolr
        mocksolr.sort_by.return_value = mocksolr
        mocksolr.exclude.return_value = mocksolr
        mocksolr.field_limit.return_value = mocksolr
        mocksolr.count.return_value = 0

        # log in as an admin
        self.assertTrue(self.client.login(**USER_CREDENTIALS['admin']))

        response = self.client.get(review_url)
        self.assertEqual("publication/review-queue.html", response.templates[0].name,
                         'non-ajax request should render with normal template')

        response = self.client.get(review_url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual("publication/snippets/review-queue.html", response.templates[0].name,
                         'ajax request should render with partial template')


    @patch('openemory.publication.views.solr_interface')
    def test_summary(self, mock_solr_interface):
        summary_url = reverse('publication:summary')
        mocksolr = MagicMock()	# required for __getitem__ / pagination
        mock_solr_interface.return_value = mocksolr
        mocksolr.query.return_value = mocksolr
        mocksolr.filter.return_value = mocksolr
        mocksolr.sort_by.return_value = mocksolr
        mocksolr.exclude.return_value = mocksolr
        mocksolr.field_limit.return_value = mocksolr
        mocksolr.count.return_value = 3	   # count required for pagination
        # results matching article stats fixture, but not most-downloaded sort order
        rval = [{'pid': 'test:3'}, {'pid': 'test:1'}, {'pid': 'test:2'}]
        mocksolr.__getitem__.return_value = rval
        mocksolr.execute.return_value = rval

        response = self.client.get(summary_url)
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for %s' % \
                         (expected, got, summary_url))

        self.assert_('newest' in response.context,
                     'list of newest articles should be set in response context')
        self.assert_('most_downloaded' in response.context,
                     'list of most downloaded articles should be set in response context')

        # check common solr query args
        # - should filter on content model & active (published) records
        # (filter is called multiple times; first time should be cmodel/active filter)
        filter_call_args = mocksolr.filter.call_args_list
        filter_kwargs = filter_call_args[0][1]
        self.assertEqual({'content_model':Article.ARTICLE_CONTENT_MODEL,
                          'state': 'A'}, filter_kwargs)
        mocksolr.field_limit.assert_called()
        # newest article search
        qargs, kwargs = mocksolr.sort_by.call_args
        self.assertEqual('-last_modified', qargs[0],
             'solr results should be sort last modified first for newest articles')

        q_call_args = mocksolr.Q.call_args_list
        q_pids = [kwargs['pid'] for args, kwargs in q_call_args if 'pid' in kwargs]
        # test stat fixture has a simple, limited set of stats
        # - pids with downloads should be in most-downloaded set and in solr pid query
        dl_articles = ArticleStatistics.objects.filter(num_downloads__gt=0)
        for a in dl_articles:
            self.assert_(a.pid in q_pids,
                 'article %s with %d downloads should be in list of solr query pids' \
                         % (a.pid, a.num_downloads))
        # - pids with 0 downloads should not be included
        undl_articles = ArticleStatistics.objects.filter(num_downloads=0)
        for a in undl_articles:
            self.assert_(a.pid not in q_pids,
                 'article %s with 0 downloads should NOT be in list of solr query pids' \
                         % (a.pid, ))
        # results should be sorted by stats, no matter what solr returns
        most_dl = response.context['most_downloaded']
        self.assertEqual('test:1', most_dl[0]['pid'],
            'solr result for most downloaded items should be sorted by stat order')
        self.assertEqual('test:2', most_dl[1]['pid'],
            'solr result for most downloaded items should be sorted by stat order')
        self.assertEqual('test:3', most_dl[2]['pid'],
            'solr result for most downloaded items should be sorted by stat order')

    @patch('openemory.publication.views.solr_interface')
    def test_browse(self, mock_solr_interface):
        mocksolr = Mock()
        mock_solr_interface.return_value = mocksolr
        mocksolr.query.return_value = mocksolr
        mocksolr.filter.return_value = mocksolr
        mocksolr.return_value = mocksolr
        mocksolr.paginate.return_value = mocksolr
        mocksolr.facet_by.return_value = mocksolr
        test_author_facets = [('Mouse, Minnie', 2), ('McDuck, Scrooge', 41)]
        test_subject_facets = [('Architecture', 3), ('Dance', 12),
                               ('Information Science', 8)]
        test_journal_facets = [('PLoS ONE', 1), ('JPEN', 2), ('Diabetes Care', 3)]
        test_creator_sorting_facets = [('mouse, minnie|Mouse, Minnie', 2),
                                       ('mcduck, scrooge|McDuck, Scrooge', 41)]
        test_researchfield_sorting_facets = [('architecture|Architecture', 3),
                                             ('dance|Dance', 12),
                                             ('information science|Information Science', 8)]
        test_journal_sorting_facets = [('plos one|PLoS ONE', 1),
                                       ('jpen|JPEN', 2),
                                       ('diabetes care|Diabetes Care', 3)]
        mocksolr.execute.return_value.facet_counts.facet_fields = {
            'creator_sorting': test_creator_sorting_facets,
            'researchfield_sorting': test_researchfield_sorting_facets,
            'journal_title_sorting': test_journal_sorting_facets,
            }
        browse_authors_url = reverse('publication:browse', args=['authors'])
        response = self.client.get(browse_authors_url)
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for %s' % \
                         (expected, got, browse_authors_url))


        # inspect Solr query opts
        mocksolr.filter.assert_called_with(content_model=Article.ARTICLE_CONTENT_MODEL,
                                           state='A')
        mocksolr.facet_by.assert_called_with('creator_sorting', mincount=1,
                                             limit=-1, sort='index', prefix='')
        mocksolr.execute.assert_called_once()
        self.assertEqual(test_author_facets, response.context['facets'])

        search_url = reverse('publication:search')
        # check for values listed/linked in response
        for val, count in test_author_facets:
            self.assertContains(response, '>%s</a> (%d)' % (val, count),
            msg_prefix='response should include facet value (as link) and count')

            # NOTE: using urrlib.quote here instead of quote_plus/urlencode
            # to match django's urlencode template filter
            self.assertContains(response, '%s?author=%s' % (search_url,
                                                            urlquote(val)),
                 msg_prefix='response should include link to author search for facet %s' \
                                % val)

        # subject browse
        browse_subject_url = reverse('publication:browse', args=['subjects'])
        response = self.client.get(browse_subject_url)
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for %s' % \
                         (expected, got, browse_subject_url))
        mocksolr.facet_by.assert_called_with('researchfield_sorting', mincount=1,
                                             limit=-1, prefix='', sort='index')
        mocksolr.execute.assert_called_once()
        self.assertEqual(test_subject_facets, response.context['facets'])
        for val, count in test_subject_facets:
            self.assertContains(response, '>%s</a> (%d)' % (val, count),
                msg_prefix='response should include facet value (as link) and ocunt')

            self.assertContains(response, '%s?subject=%s' % (search_url,
                                                            urlquote(val)),
                 msg_prefix='response should include link to subject search for facet %s' \
                                % val)

        # journal browse
        browse_journal_url = reverse('publication:browse', args=['journals'])
        response = self.client.get(browse_journal_url)
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for %s' % \
                         (expected, got, browse_journal_url))
        mocksolr.facet_by.assert_called_with('journal_title_sorting', mincount=1,
                                             limit=-1, prefix='', sort='index')
        mocksolr.execute.assert_called_once()
        self.assertEqual(test_journal_facets, response.context['facets'])
        for val, count in test_journal_facets:
            self.assertContains(response, '>%s</a> (%d)' % (val, count),
                msg_prefix='response should include facet value (as link) and ocunt')

            self.assertContains(response, '%s?journal=%s' % (search_url,
                                                            urlquote(val)),
                 msg_prefix='response should include link to journal search for facet %s' \
                                % val)




    @patch('openemory.publication.context_processors.solr_interface')
    def test_statistics_processor(self, mock_solr_interface):
        mocksolr = MagicMock()
        mock_solr_interface.return_value = mocksolr
        mocksolr.query.return_value = mocksolr
        mocksolr.filter.return_value = mocksolr
        mocksolr.paginate.return_value = mocksolr
        mocksolr.execute.return_value.result.numFound = 42

        with self._use_statistics_context():
            index_url = reverse('site-index')
            response = self.client.get(index_url)
            self.assertTrue('ARTICLE_STATISTICS' in response.context)
            self.assertTrue('total_views' in response.context['ARTICLE_STATISTICS'])
            self.assertTrue('total_downloads' in response.context['ARTICLE_STATISTICS'])
            self.assertTrue('year_views' in response.context['ARTICLE_STATISTICS'])
            self.assertTrue('year_downloads' in response.context['ARTICLE_STATISTICS'])
            self.assertEqual(42, response.context['ARTICLE_STATISTICS']['total_articles'])

    @contextmanager
    def _use_statistics_context(self):
        '''Temporarily reinstate the publication statistics context
        processor. This is normally included in settings.py, but
        testsettings.py takes it out: The context processor queries solr,
        and we don't want to have to mock out solr for every single view
        test. This context manager selectively re-enables it so that we can
        test the context processor itself.
        '''
        settings.TEMPLATE_CONTEXT_PROCESSORS.append('openemory.publication.context_processors.statistics')
        context._standard_context_processors = None
        try:
            yield
        finally:
            settings.TEMPLATE_CONTEXT_PROCESSORS.remove('openemory.publication.context_processors.statistics')
            context._standard_context_processors = None

    def test__parse_name(self):
        #several cases that are not names
        result = pubviews._parse_name(['term1'])
        self.assertEqual(result, {})
        result = pubviews._parse_name(['term1', 'term2'])
        self.assertEqual(result, {})
        result = pubviews._parse_name(['this is a phrase'])
        self.assertEqual(result, {})

        expected = {'full_name' : 'first last',
                    'first_name' : 'first',
                    'last_name' : 'last',
                    'last_first' : 'last, first',
                   }

        result = pubviews._parse_name(['first last'])
        self.assertEquals(result, expected)
        result = pubviews._parse_name(['last, first'])
        self.assertEquals(result, expected)

        expected = {'full_name' : 'first m last',
                    'first_name' : 'first m',
                    'last_name' : 'last',
                    'last_first' : 'last, first m',
                   }


        result = pubviews._parse_name(['first m last'])
        self.assertEquals(result, expected)
        result = pubviews._parse_name(['last, first m'])
        self.assertEquals(result, expected)


class QuarterlyCommandTest(TestCase):
    def test_get_article_data(self):
        #create some stats for last quarter
        c_year = date.today().year
        c_month = date.today().month
        c_quarter = year_quarter(date.today().month)

        if c_quarter == 1:
            quarter = 4
            year = c_year - 1
        else:
            quarter = c_quarter - 1
            year = c_year
        stat = ArticleStatistics(pid='managecommand:1', year=year,
             quarter=quarter, num_views=1, num_downloads=0)
        stat.save()

        stat = ArticleStatistics(pid='managecommand:2', year=year,
             quarter=quarter, num_views=5, num_downloads=2)
        stat.save()

        #these stats should not be counted becase they are not for last quarter
        stat = ArticleStatistics(pid='managecommand:3', year=c_year - 2,
             quarter=quarter, num_views=500, num_downloads=200)
        stat.save()

        #Create input for function
        articles = [
        {'pid':'managecommand:1', 'title':'Title 1'},
        {'pid':'managecommand:2', 'title':'Title 2'},
        {'pid':'managecommand:3', 'title':'Title 3'},
        ]

        C = Command()
        C.verbosity = 1
        result = C.get_article_data(articles, year, quarter)
        articles_list = result['articles_list']

        self.assertEqual(articles[0]['title'], articles_list[0]['title'])
        self.assertEqual('http://example.com/publications/managecommand:1/', articles_list[0]['url'])
        self.assertEqual(1, articles_list[0]['views'])
        self.assertEqual(0, articles_list[0]['downloads'])

        self.assertEqual(articles[1]['title'], articles_list[1]['title'])
        self.assertEqual('http://example.com/publications/managecommand:2/', articles_list[1]['url'])
        self.assertEqual(5, articles_list[1]['views'])
        self.assertEqual(2, articles_list[1]['downloads'])

        self.assertEqual(articles[2]['title'], articles_list[2]['title'])
        self.assertEqual('http://example.com/publications/managecommand:3/', articles_list[2]['url'])
        self.assertEqual(0, articles_list[2]['views'])
        self.assertEqual(0, articles_list[2]['downloads'])


        self.assertEqual(6, result['all_views'])
        self.assertEqual(2, result['all_downloads'])


    def test_send_mail(self):
        C = Command()
        C.verbosity = 1
        C.stdout = sys.stdout

        #Should not send mail when noact is true
        C.send_mail({'email': 'testuser@user.com'}, {'noact':True})
        self.assertEqual(len(mail.outbox), 0)

        C.send_mail({'email': 'testuser@user.com'}, {'noact':False})
        self.assertEqual(len(mail.outbox), 1)

        self.assertEqual(mail.outbox[0].subject, "OpenEmory Quarterly Statistics for Your Articles")
        self.assertIn('OpenEmory Administrator <openemory@listserv.cc.emory.edu>', mail.outbox[0].from_email)
        self.assertIn('testuser@user.com', mail.outbox[0].to)


class ArticleModsTest(TestCase):
    FIXTURE = '''<mods:mods xmlns:mods="http://www.loc.gov/mods/v3">
  <mods:name type="personal">
    <mods:namePart type="family">Haskell</mods:namePart>
    <mods:namePart type="given">Thomas L.</mods:namePart>
    <mods:affiliation>Emory University</mods:affiliation>
    <mods:role>
      <mods:roleTerm type="text">author</mods:roleTerm>
    </mods:role>
  </mods:name>
  <mods:name type="corporate">
    <mods:namePart>Mellon Foundation</mods:namePart>
    <mods:role>
      <mods:roleTerm type="text">funder</mods:roleTerm>
    </mods:role>
  </mods:name>
  <mods:originInfo>
    <mods:dateIssued encoding="w3cdtf" keyDate="yes">2005</mods:dateIssued>
    <mods:dateOther encoding="w3cdtf" type="embargoedUntil">2045-12-25</mods:dateOther>
  </mods:originInfo>
  <mods:relatedItem type="host">
    <mods:titleInfo>
      <mods:title>The American Historical Review</mods:title>
    </mods:titleInfo>
    <mods:originInfo>
      <mods:publisher>American Historical Association</mods:publisher>
    </mods:originInfo>
    <mods:part>
      <mods:detail type="volume">
        <mods:number>90</mods:number>
      </mods:detail>
      <mods:detail type="number">
       <mods:number>2</mods:number>
      </mods:detail>
      <mods:extent unit="pages">
        <mods:start>339</mods:start>
        <mods:end>361</mods:end>
      </mods:extent>
    </mods:part>
  </mods:relatedItem>
  <mods:relatedItem type="otherVersion" displayLabel="Final Published Version">
    <mods:identifier type="uri" displayLabel="URL">http://www.jstor.org/stable/1852669</mods:identifier>
    <mods:identifier type="doi" displayLabel="DOI">doi/10/1073/pnas/1111088108</mods:identifier>
  </mods:relatedItem>
  <mods:accessCondition type="restrictionOnAccess">Embargoed for 6 months</mods:accessCondition>
</mods:mods>'''

    def setUp(self):
        self.mods = xmlmap.load_xmlobject_from_string(self.FIXTURE, ArticleMods)

    def test_access_fields(self):
        self.assertEqual('The American Historical Review',
                         self.mods.journal.title)
        self.assertEqual('American Historical Association',
                         self.mods.journal.publisher)
        self.assertEqual('2005',
                         self.mods.publication_date)
        self.assertEqual('90', self.mods.journal.volume.number)
        self.assertEqual('2', self.mods.journal.number.number)
        self.assertEqual('339', self.mods.journal.pages.start)
        self.assertEqual('361', self.mods.journal.pages.end)
        # funder
        self.assert_(isinstance(self.mods.funders[0], FundingGroup))
        self.assertEqual('Mellon Foundation', self.mods.funders[0].name_parts[0].text)
        # authors
        self.assert_(isinstance(self.mods.authors[0], AuthorName))
        self.assertEqual('Haskell', self.mods.authors[0].family_name)
        self.assertEqual('Thomas L.', self.mods.authors[0].given_name)
        # final version
        self.assert_(isinstance(self.mods.final_version, FinalVersion))
        self.assertEqual('http://www.jstor.org/stable/1852669',
                         self.mods.final_version.url)
        self.assertEqual('doi/10/1073/pnas/1111088108',
                         self.mods.final_version.doi)
        # embargo-related fields
        self.assertEqual('2045-12-25', self.mods.embargo_end)
        self.assertEqual('Embargoed for 6 months', self.mods._embargo)
        self.assertEqual('6 months', self.mods.embargo)


    def test_create_mods_from_scratch(self):
        mymods = ArticleMods()
        mymods.authors.extend([AuthorName(family_name='Haskell', given_name='Thomas L.',
                                          affiliation='Emory University')])
        mymods.funders.extend([FundingGroup(name='NSF'), FundingGroup(name='CDC')])
        mymods.create_journal()
        mymods.journal.title = 'Nature'
        mymods.journal.publisher = 'Nature Publishing Group'
        mymods.journal.create_volume()
        mymods.journal.volume.number = 92
        mymods.journal.create_number()
        mymods.journal.number.number = 3
        mymods.journal.create_pages()
        mymods.journal.pages.start = 362
        mymods.journal.pages.end = 376

        mymods.author_notes.append(AuthorNote(text='published under a different name'))
        mymods.keywords.extend([Keyword(topic='nature'),
                                Keyword(topic='biomedical things')])
        mymods.subjects.append(ResearchField(topic='Mathematics', id='id0405'))
        mymods.version = 'Preprint: Prior to Peer Review'
        mymods.publication_date = '2008-12'
        # final version
        mymods.create_final_version()
        mymods.final_version.url = 'http://www.jstor.org/stable/1852669'
        mymods.final_version.doi = 'doi/10/1073/pnas/1111088108'
        # embargo
        mymods.embargo = '1 year'
        mymods.embargo_end = '2013-04-05'

        # static fields
        mymods.resource_type = 'text'
        mymods.genre = 'Article'
        mymods.create_physical_description()
        mymods.physical_description.media_type = 'application/pdf'

        self.assertTrue(mymods.is_valid(),
                        "MODS created from scratch should be schema-valid")

    def test_embargo(self):
        # delete
        del self.mods.embargo
        # should clear out internal mapping
        self.assertEqual(None, self.mods._embargo)
        # get method should return None
        self.assertEqual(None, self.mods.embargo)

        # set
        threeyrs = '3 years'
        self.mods.embargo = threeyrs
        # get method should return what was set
        self.assertEqual(threeyrs, self.mods.embargo)
        # internal value should end with set value
        self.assert_(self.mods._embargo.endswith(threeyrs))

        # set to None
        self.mods.embargo = None
        self.assertEqual(None, self.mods.embargo)
        self.assertEqual(None, self.mods._embargo)

    def test_funding_group(self):
        fg = FundingGroup(name='NSF')
        self.assert_(isinstance(fg, mods.Name))
        self.assertEqual('text', fg.roles[0].type)
        self.assertEqual('funder', fg.roles[0].text)
        self.assertEqual('NSF', fg.name_parts[0].text)
        self.assertEqual('corporate', fg.type)
        self.assertFalse(fg.is_empty())
        fg.name_parts[0].text = ''
        self.assertTrue(fg.is_empty())

        # empty if no name is set
        fg = FundingGroup()
        self.assertTrue(fg.is_empty())

    def test_author_name(self):
        auth = AuthorName(family_name='Haskell', given_name='Thomas L.',
                          affiliation='Emory University')
        self.assert_(isinstance(auth, mods.Name))
        self.assertEqual('personal', auth.type)
        self.assertEqual('author', auth.roles[0].text)
        self.assertEqual('Haskell', auth.family_name)
        self.assertEqual('Thomas L.', auth.given_name)
        self.assertEqual('Emory University', auth.affiliation)
        self.assertFalse(auth.is_empty())

        # empty if no name is set, even if type/role are set
        emptyauth = AuthorName()
        self.assertTrue(emptyauth.is_empty())

    def test_author_note(self):
        an = AuthorNote(text='some important little detail')
        self.assert_(isinstance(an, mods.TypedNote))
        self.assertEqual("author notes", an.type)
        self.assertEqual("some important little detail", an.text)

    def test_keyword(self):
        kw = Keyword(topic='foo')
        self.assert_(isinstance(kw, mods.Subject))
        self.assertEqual('keywords', kw.authority)
        self.assertEqual('foo', kw.topic)

    def test_supplementalMaterial(self):

        url = 'http://someurl.com'
        sup = SupplementalMaterial(url=url)
        self.assert_(isinstance(sup, SupplementalMaterial))
        self.assertEqual('references', sup.type)
        self.assertEqual('SupplementalMaterial', sup.label)

    def test_researchfield(self):
        rf = ResearchField(id='id0378', topic='Dance')
        self.assert_(isinstance(rf, mods.Subject))
        self.assertEqual('proquestresearchfield', rf.authority)
        self.assertEqual('Dance', rf.topic)
        self.assertEqual('id0378', rf.id)

    def test_publication_date(self):
        mymods = ArticleMods()
        # test that the xpath mapping sets attributes correctly
        mymods.publication_date = '2008-12'
        self.assert_(isinstance(mymods.origin_info, mods.OriginInfo))
        self.assert_(isinstance(mymods.origin_info.issued[0], mods.DateIssued))
        self.assertEqual('w3cdtf', mymods.origin_info.issued[0].encoding)
        self.assertEqual(True, mymods.origin_info.issued[0].key_date)
        self.assertEqual('2008-12', mymods.origin_info.issued[0].date)

    def test_final_version(self):
        # check xpath mappings, attributes set correctly
        mymods = ArticleMods()
        mymods.create_final_version()
        mymods.final_version.url = 'http://so.me/url'
        mymods.final_version.doi = 'doi/1/2/3'
        self.assert_(isinstance(mymods.final_version, mods.RelatedItem))
        self.assertEqual('otherVersion', mymods.final_version.type)
        self.assertEqual('Final Published Version', mymods.final_version.label)
        self.assertEqual(2, len(mymods.final_version.identifiers))
        # identifiers added in the order they are set above
        self.assertEqual('uri', mymods.final_version.identifiers[0].type)
        self.assertEqual('URL', mymods.final_version.identifiers[0].label)
        self.assertEqual('http://so.me/url', mymods.final_version.identifiers[0].text)
        self.assertEqual('doi', mymods.final_version.identifiers[1].type)
        self.assertEqual('DOI', mymods.final_version.identifiers[1].label)
        self.assertEqual('doi/1/2/3', mymods.final_version.identifiers[1].text)


    def test_relateditem_isempty(self):
        # test custom is_empty behavior for RelatedItem subtypes

        mymods = ArticleMods()
        mymods.create_final_version()
        mymods.final_version.url = 'http://so.me/url'
        mymods.final_version.doi = 'doi/1/2/3'

        self.assertFalse(mymods.final_version.is_empty())
        mymods.final_version.url = None
        mymods.final_version.doi = None
        self.assertTrue(mymods.final_version.is_empty(),
            'is_empty should return True when empty except for type & displayLabel attributes')

        self.assertFalse(self.mods.journal.is_empty())
        self.mods.journal.publisher = None
        self.mods.journal.volume = None
        self.mods.journal.number = None
        self.mods.journal.pages = None
        self.mods.journal.title = None
        # FIXME: these subfields aren't correctly recognizing when they are empty
        # should be able to remove next 3 lines and still get the right answer
        #del self.mods.journal.parts
        #del self.mods.journal.title_info
        #del self.mods.journal.origin_info
        self.assertTrue(self.mods.journal.is_empty())


    def test_calculate_embargo_end(self):
        mymods = ArticleMods()
        # no embargo duration or publication date = no action
        mymods.calculate_embargo_end()
        self.assertEqual(None, mymods.embargo_end)
        # pub date but no embargo duration
        mymods.publication_date = '2010'
        mymods.calculate_embargo_end()
        self.assertEqual(None, mymods.embargo_end)
        # embargo duration but no pub date
        mymods.embargo = '3 years'
        del mymods.publication_date
        mymods.calculate_embargo_end()
        self.assertEqual(None, mymods.embargo_end)

        # embargo end should be calculated relative to pub date
        # test the various allowed publication date formats
        # - year with no month/day
        #   - should calculate relative to beginning of next year
        mymods.publication_date = '2008'
        mymods.embargo = '1 year'
        mymods.calculate_embargo_end()
        self.assertEqual('2010-01-01', mymods.embargo_end)
        # - year/month with no day
        #   - should calculate from beginning of next month
        mymods.publication_date = '2007-12'
        mymods.calculate_embargo_end()
        self.assertEqual('2009-01-01', mymods.embargo_end)
        # - year/month/day
        mymods.publication_date = '2009-05-13'
        mymods.calculate_embargo_end()
        self.assertEqual('2010-05-13', mymods.embargo_end)

        # test various durations
        mymods.publication_date = '2010-01-01'
        mymods.embargo = '3 years'
        mymods.calculate_embargo_end()
        self.assertEqual('2013-01-01', mymods.embargo_end)
        mymods.embargo = '1 month'  # singular
        mymods.calculate_embargo_end()
        self.assertEqual('2010-02-01', mymods.embargo_end)
        mymods.embargo = '2 months' # or plural
        mymods.calculate_embargo_end()
        self.assertEqual('2010-03-01', mymods.embargo_end)
        # other durations aren't currently supported, but should work
        mymods.embargo = '1 week'
        mymods.calculate_embargo_end()
        self.assertEqual('2010-01-08', mymods.embargo_end)
        mymods.embargo = '20 days'
        mymods.calculate_embargo_end()
        self.assertEqual('2010-01-21', mymods.embargo_end)

        # no embargo: shouldn't error, end date should be cleared
        del mymods.embargo
        mymods.calculate_embargo_end()
        self.assertEqual(None, mymods.embargo_end)


class CodeListTest(TestCase):

    def setUp(self):
        self.codelist = xmlmap.load_xmlobject_from_file(lang_codelist_file,
                                                          CodeList)

    def test_access_fields(self):
        self.assertEqual('iso639-2b', self.codelist.id)
        self.assertEqual('MARC Code List for Languages', self.codelist.title)
        self.assertEqual('Network Development and MARC Standards Office, Library of Congress',
                         self.codelist.author)
        self.assertEqual('info:lc/vocabulary/languages', self.codelist.uri)
        # only 8 languages in the text fixture
        self.assertEqual(8, len(self.codelist.languages))
        self.assertEqual('Abkhaz', self.codelist.languages[0].name)
        self.assertEqual('abk', self.codelist.languages[0].code)
        self.assertEqual('info:lc/vocabulary/languages/abk',
                         self.codelist.languages[0].uri)
        self.assertEqual('Zuni', self.codelist.languages[-1].name)
        self.assertEqual('zun', self.codelist.languages[-1].code)

class LanguageCodeChoices(TestCase):

    def setUp(self):
        self.codelist = xmlmap.load_xmlobject_from_file(lang_codelist_file,
                                                        CodeList)

    @patch('openemory.publication.forms.marc_language_codelist')
    def test_language_codes(self, mocklangcodes):
        mocklangcodes.return_value = self.codelist

        langcodes = language_codes()
        self.assert_(isinstance(langcodes, SortedDict))
        mocklangcodes.assert_called_once()

        mocklangcodes.reset_mock()
        # marc_language_codelist should not be called on subsequent requests
        langcodes = language_codes()
        mocklangcodes.assert_not_called()

    @patch('openemory.publication.forms.marc_language_codelist')
    def test_language_choices(self, mocklangcodes):
        mocklangcodes.return_value = self.codelist
        opts = language_choices()
        self.assertEqual(('eng', 'English'), opts[0],
                         'english should be first language choice')
        self.assertEqual(('abk', 'Abkhaz'), opts[1])
        self.assertEqual(('zun', 'Zuni'), opts[-1])
        self.assertEqual(len(opts), len(self.codelist.languages))


class LicenseChoices(TestCase):
    fixtures = ['test-license']


    def test_license_choices(self):
        opts = license_choices()
        self.assertEqual(len(opts), 3, "should be 3 main groups of options")

        group = opts[0]
        self.assertEqual(group[0], '')
        self.assertEqual(group[1], 'no license')

        group = opts[1]
        self.assertEqual(group[0], 'Version 3.0')
        self.assertEqual(len(group[1]), 2, "should be 2 options in this group")
        opt = group[1]
        self.assertEquals(opt[0][0], "http://creativecommons.org/licenses/by/3.0/", "Value of option")
        self.assertEquals(opt[0][1], "(CC-BY 3.0) Attribution 3.0 Unported", "Label of option")
        self.assertEquals(opt[1][0], "http://creativecommons.org/licenses/by-sa/3.0/", "Value of option")
        self.assertEquals(opt[1][1], "(CC-BY-SA 3.0) Attribution-ShareAlike 3.0 Unported", "Label of option")


        group = opts[2]
        self.assertEqual(group[0], 'Version 2.0')
        self.assertEqual(len(group[1]), 1, "should be 1 options in this group")
        opt = group[1]
        self.assertEquals(opt[0][0], "http://creativecommons.org/licenses/by-nd/2.0/", "Value of option")
        self.assertEquals(opt[0][1], "(CC-BY-ND 2.0) Attribution-NoDerivs 2.0 Unported", "Label of option")


class ResearchFieldsTest(TestCase):
    rf = ResearchFields()

    def test_init(self):
        # the following values should be set after init
        self.assert_(self.rf.graph)
        self.assert_(self.rf.toplevel)
        self.assert_(self.rf.hierarchy)

    def test_label(self):
        # should work as plain text or as uriref
        self.assertEqual('Mathematics', self.rf.get_label('#0405'))
        self.assertEqual('Mathematics', self.rf.get_label(URIRef('#0405')))
        # non-existent id should not error
        self.assertEqual('', self.rf.get_label('bogus id'))


    def test_choices(self):
        choices = self.rf.as_field_choices()
        self.assert_(isinstance(choices, list))
        # check that there is only one level of list-nesting
        for c in choices:
            if isinstance(c[1], list):
                self.assert_(all(not isinstance(sc[1], list) for sc in c[1]))

    def test_get_choices(self):
        # leaf-level item (no children)
        id = '#0451'
        opt_id, opt_label = self.rf._get_choices(URIRef(id))
        self.assertEqual(id, opt_id)
        self.assertEqual('Psychology, Social', opt_label)

        # collection item with only one-level of members
        label, choices = self.rf._get_choices(URIRef('#religion'))
        self.assertEqual('Religion', label)
        self.assert_(isinstance(choices, list))
        self.assert_(['#0318', 'Religion, General'] in choices)

        # no id specified - should return from top-level
        choices = self.rf._get_choices()
        self.assert_(isinstance(choices, list))
        labels = [c[0] for c in choices]
        self.assert_('The Humanities and Social Sciences' in labels)
        self.assert_('The Sciences and Engineering' in labels)
        self.assert_(all(isinstance(c[1], list) for c in choices))


class ArticlePremisTest(TestCase):

    def test_review_event(self):
        pr = ArticlePremis()
        self.assertEqual(None, pr.review_event)
        self.assertEqual(None, pr.date_reviewed)

        # premis container needs at least one object to be valid
        pr.create_object()
        pr.object.type = 'p:representation'  # needs to be in premis namespace
        pr.object.id_type = 'ark'
        pr.object.id = 'ark:/1234/56789'

        ev = premis.Event()
        ev.id_type = 'local'
        ev.id = '01'
        ev.type = 'review'
        ev.date = '2006-06-06T00:00:00.001'
        ev.detail = 'reviewed by Ann Admynn'
        ev.agent_type = 'netid'
        ev.agent_id = 'aadmyn'
        pr.events.append(ev)
        # if changes cause validation errors, uncomment the next 2 lines to debug
        #pr.is_valid()
        #print pr.validation_errors()
        self.assert_(pr.is_valid())

        self.assertEqual(ev, pr.review_event)
        self.assertEqual(ev.date, pr.date_reviewed)

    def test_init_object(self):
        pr = ArticlePremis()
        testark = 'ark:/25534/123ab'
        pr.init_object(testark, 'ark')
        self.assertEqual(pr.object.type, 'p:representation')
        self.assertEqual(pr.object.id, testark)
        self.assertEqual(pr.object.id_type, 'ark')

    def test_premis_event(self):
        pr = ArticlePremis()
        # premis requires at least minimal object to be valid
        pr.init_object('ark:/25534/123ab', 'ark')

        mockuser = Mock()
        testreviewer = 'Ann Admyn'
        mockuser.get_profile.return_value.get_full_name.return_value = testreviewer
        mockuser.username = 'aadmyn'

        # call with invalid type
        self.assertRaises(KeyError,
                          pr.premis_event, mockuser, 'bogus', 'Reviewed by %s' % testreviewer)

        # add review event directly using premis_event function
        pr.premis_event(mockuser, 'review', 'Reviewed by %s' % testreviewer)
        # inspect the result
        self.assertEqual(1, len(pr.events))
        self.assert_(pr.review_event)
        self.assertEqual('local', pr.review_event.id_type)
        self.assertEqual('%s.ev001' % pr.object.id, pr.review_event.id)
        self.assertEqual('review', pr.review_event.type)
        self.assert_(pr.review_event.date)
        self.assertEqual('Reviewed by %s' % testreviewer,
                         pr.review_event.detail)
        self.assertEqual(mockuser.username, pr.review_event.agent_id)
        self.assertEqual('netid', pr.review_event.agent_type)

        #premis with minial object and review event should be valid
        self.assertTrue(pr.schema_valid())

#        uncomment for debugging
#        logger.info(pr.is_valid())
#        logger.info(pr.serialize(pretty=True))
#        logger.info(pr.validation_errors())

        # calling reviewed wrapper function
        pr = ArticlePremis()
        # premis requires at least minimal object to be valid
        pr.init_object('ark:/25534/123ab', 'ark')

        mockuser = Mock()
        testreviewer = 'Joe Smith'
        mockuser.get_profile.return_value.get_full_name.return_value = testreviewer
        mockuser.username = 'jsmith'

        pr.reviewed(mockuser)
        self.assertEqual(1, len(pr.events))
        self.assert_(pr.review_event)
        self.assertEqual('local', pr.review_event.id_type)
        self.assertEqual('%s.ev001' % pr.object.id, pr.review_event.id)
        self.assertEqual('review', pr.review_event.type)
        self.assert_(pr.review_event.date)
        self.assertEqual('Reviewed by %s' % testreviewer,
                         pr.review_event.detail)
        self.assertEqual(mockuser.username, pr.review_event.agent_id)
        self.assertEqual('netid', pr.review_event.agent_type)
        self.assertTrue(pr.schema_valid())

        # calling harvested wrapper function
        pr = ArticlePremis()
        # premis requires at least minimal object to be valid
        pr.init_object('ark:/25534/123ab', 'ark')

        pr.harvested(mockuser, "pmc123")
        self.assertEqual(1, len(pr.events))
        self.assert_(pr.harvest_event)
        self.assertEqual('local', pr.harvest_event.id_type)
        self.assertEqual('%s.ev001' % pr.object.id, pr.harvest_event.id)
        self.assertEqual('harvest', pr.harvest_event.type)
        self.assert_(pr.harvest_event.date)
        self.assert_(pr.date_harvested)
        self.assertEqual('Harvested pmc123 from PubMed Central by %s' % testreviewer,
                         pr.harvest_event.detail)
        self.assertEqual(mockuser.username, pr.harvest_event.agent_id)
        self.assertEqual('netid', pr.harvest_event.agent_type)
        self.assertTrue(pr.schema_valid())

        # calling updated wrapper function
        pr = ArticlePremis()
        # premis requires at least minimal object to be valid
        pr.init_object('ark:/25534/123ab', 'ark')

        # legal_statement can not be None, this simulates no selection
        pr.uploaded(mockuser, legal_statement=None)
        self.assertEqual(1, len(pr.events))
        self.assert_(pr.upload_event)
        self.assertEqual('local', pr.upload_event.id_type)
        self.assertEqual('%s.ev001' % pr.object.id, pr.upload_event.id)
        self.assertEqual('upload', pr.upload_event.type)
        self.assert_(pr.upload_event.date)
        self.assert_(pr.date_uploaded)
        self.assertTrue(('Uploaded by %s' % testreviewer) in
                         pr.upload_event.detail)
        self.assertTrue(openemory.__version__ in
                         pr.upload_event.detail)
        self.assertEqual(mockuser.username, pr.upload_event.agent_id)
        self.assertEqual('netid', pr.upload_event.agent_type)
        self.assertTrue(pr.schema_valid())


class TestFileTypeValidator(TestCase):

    def setUp(self):
        self.text_val = FileTypeValidator(types=['text/plain'])

        self.pdf_val = FileTypeValidator(types=['application/pdf'],
                                     message='Bad file!')
        self.pdf_or_text_val = FileTypeValidator(types=['application/pdf', 'text/plain'],
                                     message='Bad file!')

    def test_temporary_file(self):
        mockfile = Mock()
        mockfile.temporary_file_path.return_value = pdf_filename

        # should not raise validation error as pdf
        self.pdf_val(mockfile)
        self.pdf_or_text_val(mockfile)
        # not valid as text
        self.assertRaises(ValidationError, self.text_val, mockfile)


    def test_memory_file(self):
        data = {'content': 'this looks like plain text'}
        # valid as text
        self.text_val(data)
        self.pdf_or_text_val(data)
        # not valid as pdf
        self.assertRaises(ValidationError, self.pdf_val, data)

        class TestDataObject:
            def __init__(self, content):
                self.content = content

            def read(self):
                return self.content

        data = TestDataObject('more text')
        # valid as text
        self.text_val(data)
        self.pdf_or_text_val(data)
        # not valid as pdf
        self.assertRaises(ValidationError, self.pdf_val, data)


class TestExpireEmbargoCommand(TestCase):
    @skip('acting differently on local and jenkins')
    @patch('openemory.publication.management.commands.expire_embargo.Article')
    @patch('openemory.publication.management.commands.expire_embargo.Paginator')
    @patch('openemory.publication.management.commands.expire_embargo.solr_interface')
    def test_expire_embargo(self, mock_solr_interface, mockpaginator, mockarticle):

        results = [{'pid':'p123'}, {'pid':'p456'}, {'pid':'p789'}]

        mocksolr = MagicMock()
        mock_solr_interface.return_value = mocksolr
        mocksolr.query.return_value = mocksolr
        mocksolr.paginate.return_value = mocksolr
        mocksolr.facet_by.return_value = mocksolr
        mocksolr.filter.return_value = mocksolr
        mocksolr.exclude.return_value = mocksolr
        mocksolr.field_limit.return_value = mocksolr
        mocksolr.count.return_value = len(results)

        mockpaginator.return_value = paginator.Paginator(results, 10)
        #FIXME can't get mockarticle to reconize fulltext in indexdata return
        #mockarticle.index_data.return_value = {'fulltext': 'some text'}

        io = StringIO()
        args= ()
        options = {'pythonpath': None, 'verbosity': '1', 'traceback': None, 'noact': False, 'settings': None, 'stdout': io}
        call_command('expire_embargo', *args, **options)
        output = io.getvalue().strip()
        self.assertTrue('Total number selected: 3'in output)
        self.assertTrue('Indexed: 0'in output)
        self.assertTrue('Skipped: 3'in output)
        self.assertTrue('Errors: 0'in output)

class ArticleModsForm(TestCase):
    fixtures = ['test-license']

    def test__license_desc(self):
        form = amods(pid='fake:pid')
        result = amods._license_desc(form, "http://creativecommons.org/licenses/by/3.0/")
        self.assertIn('http://creativecommons.org/licenses/by/3.0/', result)
        self.assertIn('distribution of derivative works', result)
        self.assertIn('public display', result)
        self.assertIn('publicly performance', result)
        self.assertIn('making multiple copies', result)
        self.assertIn('credit be given to copyright holder and/or author', result)

class TestPdfObject(DigitalObject):
    pdf = FileDatastream("PDF", "PDF document", defaults={
        'versionable': False, 'mimetype': 'application/pdf'
    })
 
 
class PdfToTextTest(TestCase):
    fixture_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')
    pdf_filepath = os.path.join(fixture_dir, 'test.pdf')
    pdf_filepath2 = os.path.join(fixture_dir, 'emory_crnb7.pdf')
    pdf_text = ' \n\n \n \n \n \nThis is a test PDF document. \nIf you can read this, you have Adobe Acrobat Reader installed on your computer. \n\n \n\n'
    pdf_text2 = 'Inordertodemonstratetheconsequencesofsuchameasure'
    
    def setUp(self):
        self.repo = Repository(settings.FEDORA_ROOT, settings.FEDORA_TEST_USER,
                               settings.FEDORA_TEST_PASSWORD)
        with open(self.pdf_filepath) as pdf:
            self.pdfobj = self.repo.get_object(type=TestPdfObject)
            self.pdfobj.label = 'openemory test pdf object'
            self.pdfobj.pdf.content = pdf
            self.pdfobj.save()
            
    def tearDown(self):
        self.repo.purge_object(pid=self.pdfobj.pid)
        
    def test_file(self):
        # extract text from a pdf from a file on the local filesystem
        text = pdf_to_text(open(self.pdf_filepath, 'rb'))
        self.assertEqual(self.pdf_text, text)
  
    def test_whitespace(self):
        # extract text from a pdf from a file on the local filesystem
        text = pdf_to_text(open(self.pdf_filepath2, 'rb'))
        self.assertFalse(self.pdf_text2 in text)

    def test_object_datastream(self):
        # extract text from a pdf datastream in fedora
        pdfobj = self.repo.get_object(self.pdfobj.pid, type=TestPdfObject)
        text = pdf_to_text(pdfobj.pdf.content)
        self.assertEqual(self.pdf_text, text)
    
    def test_unicode(self):
        pdfobj = self.repo.get_object(self.pdfobj.pid, type=TestPdfObject)
        text = pdf_to_text(pdfobj.pdf.content)
        try:
            text.decode(encoding='UTF-8',errors='strict')
        except:
            self.fail("pdf_to_text result not utf-8")


class TestUtil(TestCase):

    def test_percent_match(self):
        str1 = "This is a simple string 1234567890."
        str2 = "THis@ i!s a%%    fancy string       1234567890."


        success, percent = percent_match(str1, str2, 80)
        self.assertTrue(success)

        success, percent = percent_match(str1, str2, 90)
        self.assertFalse(success)

        str1 = "This string does not match"
        str2 = "This one"

        success, percent = percent_match(str1, str2, 10)
        self.assertTrue(success)

        success, percent = percent_match(str1, str2, 50)
        self.assertFalse(success)


class TestSympDS(TestCase):

    def setUp(self):
        sympAtom_file = os.path.join(settings.BASE_DIR, 'publication', 'fixtures', 'SympAtom.xml')
        self.sympAtom = xmlmap.load_xmlobject_from_file(sympAtom_file, xmlclass=SympAtom)


    def test_basic_fields(self):
        self.assertEqual(self.sympAtom.crossref.source_name, 'crossref')
        self.assertEqual(self.sympAtom.categories, ['Publication', 'journal article'])
        self.assertEqual(self.sympAtom.embargo, 'No embargo')
        self.assertEqual(self.sympAtom.users[0].id, '3674')
        self.assertEqual(self.sympAtom.users[0].username, 'EWALLER')
        self.assertEqual(self.sympAtom.users[0].proprietary_id, 'P5699430')
        self.assertEqual(self.sympAtom.users[0].last_name, 'Waller')
        self.assertEqual(self.sympAtom.users[0].first_name, 'Edmund')
        self.assertEqual(self.sympAtom.users[0].email, 'ewaller@emory.edu')
        self.assertEqual(self.sympAtom.wos.title, 'Recombinant TLR5 Agonist CBLB502 Promotes NK Cell-Mediated Anti-CMV Immunity in Mice')
        self.assertEqual(self.sympAtom.wos.language, "English")
        self.assertTrue(self.sympAtom.pubmed.abstract.startswith('Prior work using allogeneic bone marrow'))
        self.assertEqual(self.sympAtom.wos.volume, '9')
        self.assertEqual(self.sympAtom.wos.issue, '5')
        self.assertEqual(self.sympAtom.wos.pubdate.year, '2014')
        self.assertEqual(self.sympAtom.wos.pubdate.month, '5')
        self.assertEqual(self.sympAtom.wos.pubdate.day, '30')
        self.assertEqual(self.sympAtom.pubmed.pages.begin_page, 'e96165')
        self.assertEqual(self.sympAtom.crossref.pages.end_page, 'e96170')
        self.assertEqual(self.sympAtom.wos.publisher, 'PUBLIC LIBRARY SCIENCE')
        self.assertEqual(self.sympAtom.wos.journal, 'PLOS ONE')
        self.assertEqual(self.sympAtom.wos.doi, '10.1371/journal.pone.0096165')
        self.assertEqual(self.sympAtom.wos.keywords[0], 'Science & Technology')




    def test_properties(self):
        self.assertEqual(self.sympAtom.title, 'Recombinant TLR5 Agonist CBLB502 Promotes NK Cell-Mediated Anti-CMV Immunity in Mice')
        self.assertEqual(self.sympAtom.language, ("eng", "English"))
        self.assertTrue(self.sympAtom.abstract.startswith('Prior work using allogeneic bone marrow'))
        self.assertEqual(self.sympAtom.volume, '9')
        self.assertEqual(self.sympAtom.issue, '5')
        self.assertEqual(self.sympAtom.pubdate.year, '2014')
        self.assertEqual(self.sympAtom.pubdate.month, '5')
        self.assertEqual(self.sympAtom.pubdate.day, '30')
        self.assertEqual(self.sympAtom.pubdate.date_str, '2014-05-30')
        self.assertEqual(self.sympAtom.pubdate.date_info(), ['2014', '05', '30'])
        self.assertEqual(self.sympAtom.pages.begin_page, 'e96165')
        self.assertEqual(self.sympAtom.pages.end_page, None)
        self.assertEqual(self.sympAtom.publisher, 'PUBLIC LIBRARY SCIENCE')
        self.assertEqual(self.sympAtom.journal, 'PLOS ONE')
        self.assertEqual(self.sympAtom.doi, '10.1371/journal.pone.0096165')
        self.assertEqual(self.sympAtom.keywords[0], 'Science & Technology')


