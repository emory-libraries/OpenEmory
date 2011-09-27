import logging
import os
from StringIO import StringIO

from django.conf import settings
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.test import TestCase, Client
from eulfedora.server import Repository
from eulfedora.util import RequestFailed
from eulxml import xmlmap
from mock import patch, Mock
from rdflib.graph import Graph as RdfGraph, Literal, RDF

from openemory.harvest.models import HarvestRecord
from openemory.publication.forms import UploadForm, DublinCoreEditForm
from openemory.publication.models import NlmArticle, Article
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
            #DC info
            self.article.dc.content.title = 'A very scholarly article'
            self.article.dc.content.description = 'An overly complicated description of a very scholarly article'
            self.article.dc.content.creator_list.append("Jim Smith")
            self.article.dc.content.contributor_list.append("John Smith")
            self.article.dc.content.date = "2011-08-24"
            self.article.dc.content.language = "english"
            self.article.dc.content.publisher = "Big Deal Publications"
            self.article.dc.content.rights = "you can just read it"
            self.article.dc.content.source = "wikipedia"
            self.article.dc.content.subject_list.append("scholars")
            self.article.dc.content.type = "text"
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
            expected_url = reverse('accounts:profile', kwargs={'username': TESTUSER_CREDENTIALS['username']})
            expected = 'http://testserver' + expected_url
            got = response['Location']
            self.assertEqual(expected, got,
                'Should redirect to user profile on successful upload; instead redirected to %s' % (got,))
            # make another request to get messages
            response = self.client.get(upload_url)
            messages = [ str(msg) for msg in response.context['messages'] ]
            msg = messages[0]
            self.assert_(msg.startswith("Successfully uploaded article"),
                         "successful save message set in response context")
            # pull pid from message  (at end, wrapped in tags)
            tag_start, tag_end = '<strong>', '</strong>'
            pid = msg[msg.rfind(tag_start) + len(tag_start):msg.rfind(tag_end)]
            self.pids.append(pid)	# add to list for clean-up in tearDown

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

    def test_edit_metadata(self):
        self.client.post(reverse('accounts:login'), TESTUSER_CREDENTIALS) # login

        #try a fake pid
        edit_url = reverse('publication:edit', kwargs={'pid': "fake-pid"})
        response = self.client.get(edit_url)
        expected, got = 404, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for %s (non-existent pid)' \
                % (expected, got, edit_url))

        #realpid but NOT owned by the user
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

        #now try a real pid that IS  owned by the user
        # change owner so test user can access it
        self.article.owner = TESTUSER_CREDENTIALS['username']
        self.article.save()
        self.article = self.repo.get_object(pid=self.article.pid, type=Article)

        edit_url = reverse('publication:edit', kwargs={'pid': self.article.pid})
        response = self.client.get(edit_url)
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
            'Expected %s but returned %s for %s (non-existent pid)' \
                % (expected, got, edit_url))
        self.assert_(isinstance(response.context['form'], DublinCoreEditForm),
                     'DublinCoreEditForm form should be set in response context on GET')

        #Check to make sure each value appears on the page
        self.assertContains(response, self.article.dc.content.title)
        self.assertContains(response, self.article.dc.content.description)
        self.assertContains(response,self.article.dc.content.creator[0])
        self.assertContains(response,  self.article.dc.content.contributor[0])
        self.assertContains(response, self.article.dc.content.date)
        self.assertContains(response, self.article.dc.content.language)
        self.assertContains(response, self.article.dc.content.publisher)
        self.assertContains(response, self.article.dc.content.rights)
        self.assertContains(response, self.article.dc.content.source)
        self.assertContains(response, self.article.dc.content.subject[0])
        self.assertContains(response, self.article.dc.content.type)
        self.assertContains(response, self.article.dc.content.format)
        self.assertContains(response, self.article.dc.content.identifier)

	# Blank DC form data to override
        DC_FORM_DATA = {"title" : "", "description" : "", "date" : "", "language" : "",
                        "publisher" : "", "rights" : "", "source" : "", "type" : "",
                        "format" : "", "identifier" : "",
                        "contributor_list-TOTAL_FORMS" : "2", "contributor_list-INITIAL_FORMS" : "1",
                        "contributor_list-MAX_NUM_FORMS" : "", "contributor_list-0-val" : "", 
                        "subject_list-TOTAL_FORMS" : "2", "subject_list-INITIAL_FORMS" : "1",
                        "subject_list-MAX_NUM_FORMS" : "", "subject_list-0-val" : "",
                        "creator_list-TOTAL_FORMS" : "2", "creator_list-INITIAL_FORMS" : "1",
                        "creator_list-MAX_NUM_FORMS" : "", "creator_list-0-val" : ""}


        #inalid form request due to missing required field
        data = DC_FORM_DATA.copy()
        response = self.client.post(edit_url, data)
        self.assertContains(response, "field is required")

        #good form request
        data = DC_FORM_DATA.copy()
        data["title"] = "This is the new title"
        data["description"] = "This is the new description"
        response = self.client.post(edit_url, data)
        expected, got = 303, response.status_code
        self.assertEqual(expected, got,
            'Should redirect on successful update; expected %s but returned %s for %s' \
                             % (expected, got, edit_url))
        # get newly updated version of the object to inspect
        self.article = self.repo.get_object(pid=self.article.pid, type=Article)

        # make another request to get session messages
        response = self.client.get(edit_url)
        messages = [str(m) for m in response.context['messages']]
        self.assertEqual(messages[0], "Successfully updated %s - %s" % \
                         (self.article.label, self.article.pid))
        self.assertEqual(data["title"], self.article.dc.content.title)
        self.assertEqual(data["description"], self.article.dc.content.description)
    
    @patch('openemory.publication.views.solr_interface')
    def test_search_keyword(self, mock_solr_interface):
        mocksolr = mock_solr_interface.return_value
        mocksolr.query.return_value = mocksolr
        mocksolr.field_limit.return_value = mocksolr
        mocksolr.sort_by.return_value = mocksolr

        # two articles. not testing their contents here.
        articles = [ {}, {} ]
        mocksolr.execute.return_value = articles

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
        mocksolr.sort_by.return_value = mocksolr

        # two articles. not testing their contents here.
        articles = [ {}, {} ]
        mocksolr.execute.return_value = articles

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
