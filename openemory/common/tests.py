import logging
import settings
from django.test import TestCase

from mock import patch, Mock

from pidservices.djangowrapper.shortcuts import DjangoPidmanRestClient

from openemory.common.fedora import absolutize_url
from openemory.publication.models import Article

logger = logging.getLogger(__name__)

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
        mockpidman.create_ark.return_value = self.testark

        obj = Article(Mock())
        obj.label = 'my test object'
        pid = obj.get_default_pid()
        self.assertEqual('%s-test:%s' % (settings.FEDORA_PIDSPACE, self.noid), pid)

        # ark_uri should be stored in dc.identifier
        self.assert_(self.testark in obj.dc.content.identifier_list)

        # ark_uri should be stored in descMetadata.ark_uri
        self.assert_(self.testark in obj.descMetadata.content.ark_uri)

        # ark should be stored in descMetadata.ark
        self.assert_("ark:/%s/%s" % (self.naan, self.noid) in obj.descMetadata.content.ark)
