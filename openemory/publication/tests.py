import logging
import os
from StringIO import StringIO

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.urlresolvers import reverse, resolve
from django.test import TestCase, Client
from eulfedora.server import Repository
from eulfedora.util import RequestFailed
from eulxml import xmlmap
from eulxml.xmlmap import mods
from mock import patch, Mock, MagicMock
from rdflib.graph import Graph as RdfGraph, Literal, RDF

from openemory.harvest.models import HarvestRecord
from openemory.publication.forms import UploadForm, ArticleModsEditForm, \
     validate_netid, AuthorNameForm
from openemory.publication.models import NlmArticle, Article, ArticleMods,  \
     FundingGroup, AuthorName, AuthorNote, Keyword, FinalVersion
from openemory.publication import views as pubviews
from openemory.rdfns import DC, BIBO, FRBR


TESTUSER_CREDENTIALS = {'username': 'testuser', 'password': 't3st1ng'}
# NOTE: this user must be added test Fedora users xml file for tests to pass

pdf_filename = os.path.join(settings.BASE_DIR, 'publication', 'fixtures', 'test.pdf')
pdf_md5sum = '331e8397807e65be4f838ccd95787880'
pdf_full_text = '    \n \n This is a test PDF document. If you can read this, you have Adobe Acrobat Reader installed on your computer. '

logger = logging.getLogger(__name__)

class NlmArticleTest(TestCase):

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

    def test_fulltext_available(self):
        # special property based on presence/lack of body tag
        self.assertFalse(self.article.fulltext_available)
        self.assertTrue(self.article_multiauth.fulltext_available)
        

    @patch('openemory.publication.models.EmoryLDAPBackend')
    def test_identifiable_authors(self, mockldap):
        mockldapinst = mockldap.return_value
        mockldapinst.find_user_by_email.return_value = (None, None)

        # test author with single corresponding emory author
        self.assertEqual([], self.article.identifiable_authors(),
            'should return an empty list when author not found in local DB or in LDAP')
        author_email = self.article.corresponding_author_emails[0]
        # ldap find by email should have been called
        mockldapinst.find_user_by_email.assert_called_with(author_email)
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
            self.article.pdf.content = pdf
            self.article.pdf.checksum = pdf_md5sum
            self.article.pdf.checksum_type = 'MD5'
            self.article.save()

        nxml_filename = os.path.join(settings.BASE_DIR, 'publication', 'fixtures', 'article-full.nxml')
        with open(nxml_filename) as nxml:
            self.article_nlm = self.repo.get_object(type=Article)
            self.article_nlm.label = 'A snazzy article from PubMed'
            self.article_nlm.contentMetadata.content = nxml.read()
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
        self.assertEqual(idxdata['fulltext'], pdf_full_text,
                         'article index data should include pdf text')

        idxdata = self.article_nlm.index_data()
        self.assertTrue('transcranial magnetic stimulation' in idxdata['fulltext'],
                        'article index data should include nlm body')
        self.assertTrue('interhemispheric variability' in idxdata['abstract'],
                        'article index data should include nlm abstract')

        # minimal MODS - missing fields should not be set in index data
        amods = self.article_nlm.descMetadata.content
        amods.title = 'Capitalism and the Origins of the Humanitarian Sensibility'
        idxdata = self.article_nlm.index_data()
        for field in ['funder', 'journal_title', 'journal_publisher', 'keywords',
                      'author_notes', 'pubdate', 'pubyear']:
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
        amods.author_notes.append(AuthorNote(text='First given at AHA 1943'))
        amods.publication_date = '2001-05-29'
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
        self.assertEqual([amods.author_notes[0].text], idxdata['author_notes'])
        self.assertEqual('2001', idxdata['pubyear'])
        self.assertEqual(amods.publication_date, idxdata['pubdate'])


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
    fixtures =  ['testusers']

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
        # invalid post - no file
        response = self.client.post(upload_url)
        self.assertContains(response, 'field is required',
             msg_prefix='required field message should be displayed when the form is submitted without data')

        # POST a test pdf
        with open(pdf_filename) as pdf:
            response = self.client.post(upload_url, {'pdf': pdf})
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
            self.assert_(msg.startswith("Successfully uploaded PDF"),
                         "successful save message set in response context")
            self.assert_('Please enter article information' in msg,
                         "edit metadata instruction included in success message")

        # inspect created object
        obj = self.repo.get_object(pid, type=Article)
        # check object initialization
        self.assertEqual('test.pdf', obj.label)
        self.assertEqual('test.pdf', obj.dc.content.title)
        self.assertEqual(TESTUSER_CREDENTIALS['username'], obj.owner)
        self.assertEqual('application/pdf', obj.pdf.mimetype)
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
                response = self.client.post(upload_url, {'pdf': pdf})
                self.assertContains(response, 'error uploading your document')
                messages = [ str(msg) for msg in response.context['messages'] ]
                self.assertEqual(0, len(messages),
                    'no success messages set when ingest errors')

    def test_ingest_from_harvestrecord(self):
        # test ajax post to ingest from havest queue
        
        # not logged in
        ingest_url = reverse('publication:ingest')
        response = self.client.post(ingest_url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        expected, got = 401, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for %s (not logged in)' \
                % (expected, got, ingest_url))

        # login as admin test user for remaining tests
        self.client.post(reverse('accounts:login'), TESTUSER_CREDENTIALS)

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

        # only check custom logic implemented here
        # (not testing eulfedora.views.raw_datastream logic)
        content_disposition = response['Content-Disposition']
        self.assert_(content_disposition.startswith('attachment; '),
                     'content disposition should be set to attachment, to prompt download')
        # PRELIMINARY download filename.....
        self.assert_(content_disposition.endswith('%s.pdf' % self.article.pid),
                     'content disposition filename should be a .pdf based on object pid')

        # cursory check on content
        with open(pdf_filename) as pdf:
            self.assertEqual(pdf.read(), response.content)

    @patch('openemory.publication.forms.EmoryLDAPBackend')
    def test_edit_metadata(self, mockldap):
        self.client.post(reverse('accounts:login'), TESTUSER_CREDENTIALS) # login

        # non-existent pid should 404
        edit_url = reverse('publication:edit', kwargs={'pid': "fake-pid"})
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
            'version': 'preprint',
            'publication_date_year': '2005',
            'publication_date_month': '01',
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
        self.assertContains(response, "This URL appears to be a broken link",
             msg_prefix='form displays an error when an invalid URL is entered')
        self.assertContains(response, "Enter a valid value",
             msg_prefix='form displays an error when DOI does not match regex')

        # post minimum required fields
        data = MODS_FORM_DATA.copy()
        response = self.client.post(edit_url, data)
        expected, got = 303, response.status_code
        self.assertEqual(expected, got,
            'Should redirect on successful update; expected %s but returned %s for %s' \
                             % (expected, got, edit_url))
        self.assertEqual('http://testserver' + reverse('accounts:profile',
                                 kwargs={'username': TESTUSER_CREDENTIALS['username']}),
                         response['Location'],
             'should redirect to user profile page after save')
        # get newly updated version of the object to inspect
        self.article = self.repo.get_object(pid=self.article.pid, type=Article)
        self.assertEqual(MODS_FORM_DATA['title_info-title'],
                         self.article.descMetadata.content.title_info.title)
        self.assertEqual(MODS_FORM_DATA['journal-title'],
                         self.article.descMetadata.content.journal.title)
        self.assertEqual(MODS_FORM_DATA['journal-publisher'],
                         self.article.descMetadata.content.journal.publisher)
        self.assertEqual(MODS_FORM_DATA['version'],
                         self.article.descMetadata.content.version)
        # non-required, empty fields should not be present in xml
        self.assertEqual(None, self.article.descMetadata.content.abstract)
        self.assertEqual(None, self.article.descMetadata.content.journal.volume)
        self.assertEqual(None, self.article.descMetadata.content.journal.number)
        self.assertEqual(0, len(self.article.descMetadata.content.funders))
        self.assertEqual(0, len(self.article.descMetadata.content.author_notes))

        # make another request to check session message
        response = self.client.get(edit_url)
        messages = [str(m) for m in response.context['messages']]
        self.assertEqual(messages[0], "Saved %s" % self.article.label)

        # post full metadata
        data = MODS_FORM_DATA.copy()
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
            'final_version-doi': 'doi:10.34/test/valid/doi'

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
    
    @patch('openemory.publication.views.solr_interface')
    def test_search_keyword(self, mock_solr_interface):
        mocksolr = mock_solr_interface.return_value
        mocksolr.query.return_value = mocksolr
        mocksolr.field_limit.return_value = mocksolr
        mocksolr.highlight.return_value = mocksolr
        mocksolr.sort_by.return_value = mocksolr

        articles = mocksolr.execute.return_value = MagicMock()

        search_url = reverse('publication:search')
        response = self.client.get(search_url, {'keyword': 'cheese'})
        
        self.assertEqual(mocksolr.query.call_args_list, 
            [ ((), {'content_model': Article.ARTICLE_CONTENT_MODEL}),
              (('cheese',), {}) ])
        self.assertEqual(mocksolr.execute.call_args_list,
            [ ((), {}) ])

        self.assertEqual(response.context['results'], articles)
        self.assertEqual(response.context['search_terms'], ['cheese'])

    @patch('openemory.publication.views.solr_interface')
    def test_search_phrase(self, mock_solr_interface):
        mocksolr = mock_solr_interface.return_value
        mocksolr.query.return_value = mocksolr
        mocksolr.field_limit.return_value = mocksolr
        mocksolr.highlight.return_value = mocksolr
        mocksolr.sort_by.return_value = mocksolr

        articles = mocksolr.execute.return_value = MagicMock()

        search_url = reverse('publication:search')
        response = self.client.get(search_url, {'keyword': 'cheese "sharp cheddar"'})
        
        self.assertEqual(mocksolr.query.call_args_list, 
            [ ((), {'content_model': Article.ARTICLE_CONTENT_MODEL}),
              (('cheese', 'sharp cheddar'), {}),
            ])
        self.assertEqual(mocksolr.execute.call_args_list,
            [ ((), {}) ])

        self.assertEqual(response.context['results'], articles)
        self.assertEqual(response.context['search_terms'], ['cheese', 'sharp cheddar'])


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
        mymods.version = 'preprint'
        mymods.publication_date = '2008-12'
        # final version
        mymods.create_final_version()
        mymods.final_version.url = 'http://www.jstor.org/stable/1852669'
        mymods.final_version.doi = 'doi/10/1073/pnas/1111088108'
        # static fields
        mymods.resource_type = 'text'
        mymods.genre = 'Article'
        mymods.create_physical_description()
        mymods.physical_description.media_type = 'application/pdf'

        self.assertTrue(mymods.is_valid(),
                        "MODS created from scratch should be schema-valid")

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
        
