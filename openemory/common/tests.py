# file openemory/common/tests.py
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

from datetime import datetime
import logging
import os
from django.conf import settings
from urlparse import urlsplit, parse_qs

from django.test import TestCase
from mock import patch, Mock

from pidservices.djangowrapper.shortcuts import DjangoPidmanRestClient
from eulxml.xmlmap import load_xmlobject_from_file

from openemory.common import romeo
from openemory.common.fedora import absolutize_url
from openemory.publication.models import Publication

logger = logging.getLogger(__name__)
DIR_NAME = os.path.dirname(__file__)

class DigitalObjectTests(TestCase):
    naan = '123'
    noid = 'bcd'
    testark = 'http://p.id/ark:/%s/%s' % (naan, noid)

    def test_absolutize_url(self):

        base = 'http://example.com'
        uri = '/some/weird/url'
        expected = '%s%s' % (base, uri)

        result = absolutize_url(uri)
        self.assertEquals(result, expected)
        result = absolutize_url('%s%s' % (base, uri))
        self.assertEquals(result, expected)


    @patch('openemory.common.fedora.pidman')
    def test_get_default_pid(self, mockpidman):
        # TODO: use override_settings once we get to django 1.6+
        # for now, manually add settings for testing
        _pidman_host = getattr(settings, 'PIDMAN_HOST', None)
        _pidman_domain = getattr(settings, 'PIDMAN_DOMAIN', None)

        settings.PIDMAN_HOST = 'http://pid.co'
        settings.PIDMAN_DOMAIN = 'http://pid.co/domains/123'

        mockpidman.create_ark.return_value = self.testark

        obj = Publication(Mock())
        obj.label = 'my test object'
        pid = obj.get_default_pid()
        self.assertEqual('%s:%s' % (settings.FEDORA_PIDSPACE, self.noid), pid)

        # ark_uri should be stored in dc.identifier
        self.assert_(self.testark in obj.dc.content.identifier_list)

        # ark_uri should be stored in descMetadata.ark_uri
        self.assert_(self.testark in obj.descMetadata.content.ark_uri)

        # ark should be stored in descMetadata.ark
        self.assert_("ark:/%s/%s" % (self.naan, self.noid) in obj.descMetadata.content.ark)

        settings.PIDMAN_HOST = _pidman_host
        settings.PIDMAN_DOMAIN = _pidman_domain

    def test_noid(self):
        A = Publication(Mock())
        A.pid="test:efg12"
        self.assertEqual(A.noid, 'efg12')

class RomeoTests(TestCase):
    fixtures_dir = os.path.join(DIR_NAME, 'fixtures', 'romeo')
    def fixture_text(self, fname):
        fpath = os.path.join(self.fixtures_dir, fname)
        with open(fpath) as fobj:
            return fobj.read()

    # these examples follow the examples in the docs at:
    # http://www.sherpa.ac.uk/romeo/SHERPA%20RoMEO%20API%20V-2-4%202009-10-29.pdf

    @patch('openemory.common.romeo.urlopen')
    def test_search_publisher_name_example(self, mock_urlopen):
        mock_urlopen.return_value.read.return_value = \
                self.fixture_text('example-02.xml')

        publishers = romeo.search_publisher_name('institute of physics')

        # query
        mock_urlopen.assert_called_once()
        args, kwargs = mock_urlopen.call_args
        self.assertEqual(kwargs, {})
        self.assertEqual(len(args), 1)
        query_args = parse_qs(urlsplit(args[0]).query)
        self.assertEqual(query_args['pub'], ['institute of physics'])

        # response
        self.assertEqual(len(publishers), 2)
        self.assertEqual(publishers[0].id, '7')
        self.assertEqual(publishers[0].name, 'American Institute of Physics')
        self.assertEqual(publishers[0].url, 'http://www.aip.org/')
        self.assertEqual(publishers[0].preprint_archiving, 'can')
        self.assertEqual(publishers[0].postprint_archiving, 'can')
        self.assertEqual(len(publishers[0].conditions), 6)
        self.assertEqual(publishers[0].conditions[0], 'Publishers version/PDF ' +
                'may be used on authors personal or institutional website')
        self.assertEqual(publishers[0].paid_access_url,
                'http://journals.aip.org/au_select.html')
        self.assertEqual(publishers[0].paid_access_name, 'Author Select')
        self.assertEqual(len(publishers[0].copyright_links), 1)
        self.assertEqual(publishers[0].copyright_links[0].text, 'Policy')
        self.assertEqual(publishers[0].copyright_links[0].url,
                'http://www.aip.org/pubservs/web_posting_guidelines.html')
        self.assertEqual(publishers[0].romeo_colour, 'green')
        self.assertEqual(publishers[0].date_added, datetime(2004, 1, 10, 0))
        self.assertEqual(publishers[0].date_updated, datetime(2009, 10, 27, 14, 35, 36))

        self.assertEqual(publishers[1].id, '40')
        self.assertEqual(publishers[1].name, 'Institute of Physics')
        # etc. elements work the same as for the first publisher.

    @patch('openemory.common.romeo.urlopen')
    def test_search_publisher_id_example(self, mock_urlopen):
        mock_urlopen.return_value.read.return_value = \
                self.fixture_text('example-03.xml')

        publisher = romeo.search_publisher_id('3')

        # query
        mock_urlopen.assert_called_once()
        args, kwargs = mock_urlopen.call_args
        self.assertEqual(kwargs, {})
        self.assertEqual(len(args), 1)
        query_args = parse_qs(urlsplit(args[0]).query)
        self.assertEqual(query_args['id'], ['3'])

        # response
        self.assertTrue(isinstance(publisher, romeo.Publisher))
        self.assertEqual(publisher.id, '3')
        self.assertEqual(publisher.name, 'American Association for the Advancement of Science')
        # nothing else in here that isn't covered in other tests

    @patch('openemory.common.romeo.urlopen')
    def test_search_journal_title_multiple_example(self, mock_urlopen):
        mock_urlopen.return_value.read.return_value = \
                self.fixture_text('example-04.xml')

        journals = romeo.search_journal_title('dna')

        # query
        mock_urlopen.assert_called_once()
        args, kwargs = mock_urlopen.call_args
        self.assertEqual(kwargs, {})
        self.assertEqual(len(args), 1)
        query_args = parse_qs(urlsplit(args[0]).query)
        self.assertEqual(query_args['jtitle'], ['dna'])

        # response
        self.assertEqual(len(journals), 5)
        self.assertEqual(journals[0].title, 'DNA')
        self.assertEqual(journals[0].issn, '0198-0238')
        self.assertEqual(journals[1].title, 'DNA and Cell Biology')
        self.assertEqual(journals[1].issn, '1044-5498')
        self.assertEqual(journals[1].publisher_zetoc, 'Mary Ann Liebert, Inc.')
        self.assertEqual(journals[1].publisher_romeo, 'Mary Ann Liebert')

    @patch('openemory.common.romeo.urlopen')
    def test_search_journal_title_single_example(self, mock_urlopen):
        mock_urlopen.return_value.read.return_value = \
                self.fixture_text('example-05.xml')

        journals = romeo.search_journal_title('revista argentina de cardiologia')
        publisher = journals[0].publisher_details()

        # query
        mock_urlopen.assert_called_once()
        args, kwargs = mock_urlopen.call_args
        self.assertEqual(kwargs, {})
        self.assertEqual(len(args), 1)
        query_args = parse_qs(urlsplit(args[0]).query)
        self.assertEqual(query_args['jtitle'], ['revista argentina de cardiologia'])

        # response
        self.assertEqual(len(journals), 1)
        self.assertEqual(journals[0].title, 'Revista Argentina de Cardiologia')
        self.assertEqual(journals[0].issn, '0034-7000')
        self.assertTrue(isinstance(publisher, romeo.Publisher))
        self.assertEqual(publisher.name, u'Sociedad Argentina de Cardiolog\xeda')

    @patch('openemory.common.romeo.urlopen')
    def test_search_journal_issn_with_journal(self, mock_urlopen):
        mock_urlopen.return_value.read.return_value = \
                self.fixture_text('example-06.xml')

        journal = romeo.search_journal_issn('0013-1245')
        publisher = journal.publisher_details()

        # query
        mock_urlopen.assert_called_once()
        args, kwargs = mock_urlopen.call_args
        self.assertEqual(kwargs, {})
        self.assertEqual(len(args), 1)
        query_args = parse_qs(urlsplit(args[0]).query)
        self.assertEqual(query_args['issn'], ['0013-1245'])

        # response
        self.assertEqual(journal.title, 'Education and Urban Society')
        self.assertEqual(journal.issn, '0013-1245')
        self.assertTrue(isinstance(publisher, romeo.Publisher))
        self.assertEqual(publisher.name, 'SAGE Publications')
        # also some publisher fields we haven't seen before
        self.assertEqual(len(publisher.postprint_restrictions), 1)
        self.assertEqual(publisher.postprint_restrictions[0],
                '<num>12</num> <period units="month">months</period> embargo')

    @patch('openemory.common.romeo.urlopen')
    def test_search_journal_issn_no_publisher(self, mock_urlopen):
        mock_urlopen.return_value.read.return_value = \
                self.fixture_text('example-07.xml')

        journal = romeo.search_journal_issn('0004-9158')

        # query
        mock_urlopen.assert_called_once()
        args, kwargs = mock_urlopen.call_args
        self.assertEqual(kwargs, {})
        self.assertEqual(len(args), 1)
        query_args = parse_qs(urlsplit(args[0]).query)
        self.assertEqual(query_args['issn'], ['0004-9158'])

        # response
        self.assertEqual(journal.title, 'Australian Forestry')
        self.assertEqual(journal.issn, '0004-9158')
        self.assertFalse(journal.response_includes_publisher_details())

    @patch('openemory.common.romeo.urlopen')
    def test_search_journal_title_no_match(self, mock_urlopen):
        mock_urlopen.return_value.read.return_value = \
                self.fixture_text('example-08.xml')

        journals = romeo.search_journal_title('recycling journal')

        # query
        mock_urlopen.assert_called_once()
        args, kwargs = mock_urlopen.call_args
        self.assertEqual(kwargs, {})
        self.assertEqual(len(args), 1)
        query_args = parse_qs(urlsplit(args[0]).query)
        self.assertEqual(query_args['jtitle'], ['recycling journal'])

        # response
        self.assertEqual(len(journals), 0)
