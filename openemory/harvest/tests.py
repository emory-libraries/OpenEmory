import os

from django.core.urlresolvers import reverse
from django.contrib.auth.models import User, Group
from django.test import TestCase
from mock import patch, Mock
from eulxml import xmlmap

from openemory.accounts.tests import USER_CREDENTIALS
from openemory.harvest.entrez import EFetchArticle, EFetchResponse
from openemory.harvest.models import OpenEmoryEntrezClient, HarvestRecord


def fixture_path(fname):
    # Shared utility method used by multiple tests
    # generate an absolute path to a file in the fixtures directory
    return os.path.join(os.path.dirname(__file__), 'fixtures', fname)


class HarvestViewsTest(TestCase):
    fixtures =  ['users']	# re-using fixture from accounts

    def test_queue(self):
        queue_url = reverse('harvest:queue')
        response = self.client.get(queue_url)
        expected, got = 401, response.status_code
        self.assertEqual(expected, got,
            "expected status code %s but got %s for %s as anonymous user" \
                % (expected, got, queue_url))
        
        # log in as non-admin staff
        self.assertTrue(self.client.login(**USER_CREDENTIALS['staff']))
        response = self.client.get(queue_url)
        expected, got = 403, response.status_code
        self.assertEqual(expected, got,
            "expected status code %s but got %s for %s as non-admin user" \
                % (expected, got, queue_url))

        # log in as an admin
        self.assertTrue(self.client.login(**USER_CREDENTIALS['admin']))
        response = self.client.get(queue_url)
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
            "expected status code %s but got %s for %s as site admin user" \
                % (expected, got, queue_url))
        # test that the page displays
        self.assertContains(response, 'Harvested Records')


class EntrezTest(TestCase):
    def setUp(self):
        self.entrez = OpenEmoryEntrezClient()

    @patch('openemory.harvest.entrez.sleep')
    @patch('openemory.harvest.entrez.xmlmap')
    def test_get_emory_articles(self, mock_xmlmap, mock_sleep):
        '''Verify that test_emory_articles makes an appropriate request to
        E-Utils and interprets the result appropriately.'''

        # set up mocks
        def mock_load(url, xmlclass):
            '''mock-like method wrapping load_xmlobject_from_file without
            actually making a network query, but still calling the requested
            xmlclass constructor.
            '''
            # figure out what fixture to return
            fixture = (mock_load.return_fixtures[mock_load.call_count]
                       if mock_load.call_count < len(mock_load.return_fixtures)
                       else mock_load.return_fixtures[-1])

            mock_load.call_count += 1
            mock_load.urls.append(url)
            test_response_path = fixture_path(fixture)
            test_response_obj = xmlmap.load_xmlobject_from_file(test_response_path,
                    xmlclass=xmlclass)
            return test_response_obj
        mock_load.call_count = 0
        mock_load.urls = []
        mock_xmlmap.load_xmlobject_from_file = mock_load
        # configure the return values
        mock_load.return_fixtures = [
            'esearch-response-withhist.xml',
            'efetch-retrieval-from-hist.xml',
            ]

        # make the call
        articles = self.entrez.get_emory_articles()

        self.assertEqual(mock_xmlmap.load_xmlobject_from_file.call_count, 2)
        # check that we slept between calls (reqd by eutils policies)
        self.assertEqual(mock_sleep.call_count, 1)
        sleep_args, sleep_kwargs = mock_sleep.call_args
        self.assertTrue(sleep_args[0] >= 0.3)
        # check the first query url
        self.assertTrue('esearch.fcgi' in mock_load.urls[0])
        # these should always be in there per E-Utils policy (see entrez.py)
        self.assertTrue('tool=' in mock_load.urls[0])
        self.assertTrue('email=' in mock_load.urls[0])
        # these are what we're currently querying for. note that these may
        # change as our implementation develops. if they do (causing these
        # assertions to fail) then we probably need to update our fixture.
        self.assertTrue('db=pmc' in mock_load.urls[0])
        self.assertTrue('term=emory' in mock_load.urls[0])
        self.assertTrue('field=affl' in mock_load.urls[0])
        self.assertTrue('usehistory=y' in mock_load.urls[0])

        # check the second query url
        self.assertTrue('efetch.fcgi' in mock_load.urls[1])
        # always required
        self.assertTrue('tool=' in mock_load.urls[1])
        self.assertTrue('email=' in mock_load.urls[1])
        # what we're currently querying for
        self.assertTrue('db=pmc' in mock_load.urls[1])
        self.assertTrue('usehistory=y' in mock_load.urls[1])
        self.assertTrue('query_key=' in mock_load.urls[1])
        self.assertTrue('WebEnv=' in mock_load.urls[1])
        self.assertTrue('retmode=xml' in mock_load.urls[1])
        self.assertTrue('retstart=' in mock_load.urls[1])
        self.assertTrue('retmax=' in mock_load.urls[1])

        # check return parsing. values from the fixture
        self.assertEqual(len(articles), 20)
        # article field testing handled below in EFetchArticleTest



class EFetchArticleTest(TestCase):

    def setUp(self):
        article_fixture_path = fixture_path('efetch-retrieval-from-hist.xml')
        self.fetch_response = xmlmap.load_xmlobject_from_file(article_fixture_path,
                                                              xmlclass=EFetchResponse)

        # one corresponding author with an emory email
        self.article = self.fetch_response.articles[0]

        # 4 emory authors, email in author instead of corresponding author info
        self.article_multiauth = self.fetch_response.articles[13]

        # non-emory author
        self.article_nonemory = self.fetch_response.articles[8]

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
        self.assertEqual(self.fetch_response.articles[19].pmid, 20386883)

    def test_fulltext_available(self):
        # special property based on presence/lack of body tag
        self.assertFalse(self.article.fulltext_available)
        self.assertTrue(self.article_multiauth.fulltext_available)
        

    @patch('openemory.harvest.entrez.EmoryLDAPBackend')
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


class HarvestRecordTest(TestCase):
    
    def setUp(self):
        article_fixture_path = fixture_path('efetch-retrieval-from-hist.xml')
        self.fetch_response = xmlmap.load_xmlobject_from_file(article_fixture_path,
                                                              xmlclass=EFetchResponse)
        # one corresponding author with an emory email
        self.article = self.fetch_response.articles[0]

    def test_init_from_fetched_article(self):
        # mock identifiable authors to avoid actual look-up
        with patch.object(self.article, 'identifiable_authors', new=Mock(return_value=[])):
            record = HarvestRecord.init_from_fetched_article(self.article)
            self.assertEqual(self.article.article_title, record.title)
            self.assertEqual(self.article.docid, record.pmcid)
            self.assertEqual(self.article.fulltext_available, record.fulltext)
            self.assertEqual(0, record.authors.count())
            # remove the new record so we can test creating it again
            record.delete()

        # simulate identifiable authors 
        testauthor = User(username='author')
        testauthor.save()
        with patch.object(self.article, 'identifiable_authors',
                          new=Mock(return_value=[testauthor])):
            record = HarvestRecord.init_from_fetched_article(self.article)
            self.assertEqual(1, record.authors.count())
            self.assert_(testauthor in record.authors.all())
            
        
