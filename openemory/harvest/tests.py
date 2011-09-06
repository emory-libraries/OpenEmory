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

    @patch('openemory.harvest.entrez.xmlmap')
    def test_get_emory_articles(self, mock_xmlmap):
        '''Verify that test_emory_articles makes an appropriate request to
        E-Utils and interprets the result appropriately.'''

        # set up mocks
        def mock_load(url, xmlclass):
            '''mock-like method wrapping load_xmlobject_from_file without
            actually making a network query, but still calling the requested
            xmlclass constructor.
            '''
            mock_load.call_count += 1
            mock_load.url = url
            test_response_path = self.fixture_path('esearch-response-basic.xml')
            test_response_obj = xmlmap.load_xmlobject_from_file(test_response_path,
                    xmlclass=xmlclass)
            return test_response_obj
        mock_load.call_count = 0
        mock_xmlmap.load_xmlobject_from_file = mock_load

        # make the call
        actual_response = self.entrez.get_emory_articles()

        # check the query url
        self.assertEqual(mock_xmlmap.load_xmlobject_from_file.call_count, 1)
        # these should always be in there per E-Utils policy (see entrez.py)
        self.assertTrue('tool=' in mock_load.url)
        self.assertTrue('email=' in mock_load.url)
        # these are what we're currently querying for. note that these may
        # change as our implementation develops. if they do (causing these
        # assertions to fail) then we probably need to update our fixture.
        self.assertTrue('db=pmc' in mock_load.url)
        self.assertTrue('term=emory' in mock_load.url)
        self.assertTrue('field=affl' in mock_load.url)

        # check return parsing. values from the fixture
        self.assertEqual(actual_response.count, 7557)
        self.assertEqual(len(actual_response.docid), 20)
        self.assertTrue(2701312 in actual_response.docid)
        self.assertTrue(2874656 in actual_response.docid)
