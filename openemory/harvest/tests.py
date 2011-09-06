import os

from django.core.urlresolvers import reverse
from django.contrib.auth.models import User, Group
from django.test import TestCase
from mock import patch
from eulxml import xmlmap

from openemory.accounts.tests import USER_CREDENTIALS
from openemory.harvest.models import OpenEmoryEntrezClient

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

    def fixture_path(self, fname):
        return os.path.join(os.path.dirname(__file__), 'fixtures', fname)

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
            test_response_path = self.fixture_path(fixture)
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
        self.assertEqual(articles[0].docid, 2701312)
        self.assertEqual(articles[0].pmid, 18446447)
        self.assertEqual(articles[0].journal_title, "Cardiovascular toxicology")
        self.assertEqual(articles[0].article_title, "Cardiac-Targeted Transgenic Mutant Mitochondrial Enzymes")
        self.assertEqual(len(articles[0].authors), 17)
        self.assertEqual(articles[0].authors[0].surname, 'Kohler')
        self.assertEqual(articles[0].authors[0].given_names, 'James J.')
        self.assertTrue('Pathology, Emory' in articles[0].authors[0].affiliation)
        self.assertEqual(articles[0].authors[16].surname, 'Lewis')
        self.assertEqual(articles[0].corresponding_author_email, 'jjkohle@emory.edu')
        self.assertEqual(articles[19].pmid, 20386883)
