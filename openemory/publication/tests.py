from django.conf import settings
from django.core.urlresolvers import reverse
from django.test import TestCase, Client
from eulfedora.server import Repository
from eulfedora.util import RequestFailed
import logging
from mock import patch, Mock
from os import path
from rdflib.graph import Graph as RdfGraph, Literal, RDF

from openemory.publication.forms import UploadForm
from openemory.publication.models import Article
from openemory.rdfns import DC, BIBO, FRBR

TESTUSER_CREDENTIALS = {'username': 'testuser', 'password': 't3st1ng'}
# NOTE: this user must be added test Fedora users xml file for tests to pass

pdf_filename = path.join(settings.BASE_DIR, 'publication', 'fixtures', 'test.pdf')
pdf_md5sum = '331e8397807e65be4f838ccd95787880'

logger = logging.getLogger(__name__)

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
        
        self.pids = [self.article.pid]

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
        

class PublicationViewsTest(TestCase):
    fixtures =  ['testusers']

    def setUp(self):
        self.repo = Repository(username=settings.FEDORA_TEST_USER,
                                     password=settings.FEDORA_TEST_PASSWORD)
        self.client = Client()

        # create a test article object to use in tests
        with open(pdf_filename) as pdf:
            self.article = self.repo.get_object(type=Article)
            self.article.label = 'A very scholarly article'
            self.article.pdf.content = pdf
            self.article.pdf.checksum = pdf_md5sum
            self.article.pdf.checksum_type = 'MD5'
            self.article.save()
        
        self.pids = [self.article.pid]

    def tearDown(self):
        for pid in self.pids:
            try:
                self.repo.purge_object(pid)
            except RequestFailed:
                logger.warn('Failed to purge test object %s' % pid)

    def test_upload(self):
        # not logged in
        upload_url = reverse('publication:upload')
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
            response = self.client.post(upload_url, {'pdf': pdf}, follow=True)  # follow redirect
            self.assert_(response.redirect_chain, 'upload should redirect on successful upload')
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


            
        
