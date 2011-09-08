import os

from django.core.urlresolvers import reverse
from django.contrib.auth.models import User, Group
from django.test import TestCase
from mock import patch, Mock
from eulxml import xmlmap

from openemory.accounts.tests import USER_CREDENTIALS
from openemory.harvest.entrez import (EntrezClient, ArticleQuerySet,
    EFetchResponse, ESearchResponse)
from openemory.harvest.models import OpenEmoryEntrezClient, HarvestRecord


def fixture_path(fname):
    # Shared utility method used by multiple tests
    # generate an absolute path to a file in the fixtures directory
    return os.path.join(os.path.dirname(__file__), 'fixtures', fname)


class HarvestViewsTest(TestCase):
    fixtures =  ['users',	# re-using fixture from accounts
                 'harvest_authors', 'harvest_records']
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
        # test that harvested records display correctly
        for record in HarvestRecord.objects.filter(status='harvested').all():
            self.assertContains(response, record.title,
                msg_prefix='harvested record title should display on queue')
            self.assertContains(response, record.access_url,
                msg_prefix='harvested record PMC link should display on queue')
            for author in record.authors.all():
                self.assertContains(response, author.get_full_name(),
                    msg_prefix='record author full name should be included in queue')
                self.assertContains(response, reverse('accounts:profile',
                                                      kwargs={'username': author.username}),
                    msg_prefix='record author profile link should be included in queue')
        # test that *ingested* harvest records are not included
        for record in HarvestRecord.objects.filter(status='ingested').all():
            self.assertNotContains(response, record.title,
                msg_prefix='ingested harvest record title should not display on queue')
        

        fulltext_count = HarvestRecord.objects.filter(fulltext=True).count()
        self.assertContains(response, 'full text available', fulltext_count,
            msg_prefix='full text available should appear once for each full text record')
                             


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
        article_qs = self.entrez.get_emory_articles()

        self.assertEqual(mock_xmlmap.load_xmlobject_from_file.call_count, 1)
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

        # fetch one
        articles = article_qs[:20] # grab a slice to limit the query
        articles[0]

        self.assertEqual(mock_xmlmap.load_xmlobject_from_file.call_count, 2)
        # check that we slept between calls (reqd by eutils policies)
        self.assertEqual(mock_sleep.call_count, 1)
        sleep_args, sleep_kwargs = mock_sleep.call_args
        self.assertTrue(sleep_args[0] >= 0.3)
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
        self.assertTrue('retstart=0' in mock_load.urls[1])
        self.assertTrue('retmax=20' in mock_load.urls[1])

        # article field testing handled below in EFetchArticleTest


class ArticleQuerySetTest(TestCase):
    def fixture_path(self, fname):
        return os.path.join(os.path.dirname(__file__), 'fixtures', fname)

    def setUp(self):
        search_fixture_path = self.fixture_path('esearch-response-withhist.xml')
        self.search_response = xmlmap.load_xmlobject_from_file(search_fixture_path,
                xmlclass=ESearchResponse)

        fetch_fixture_path = self.fixture_path('efetch-retrieval-from-hist.xml')
        self.fetch_response = xmlmap.load_xmlobject_from_file(fetch_fixture_path,
                xmlclass=EFetchResponse)

        self.mock_client = Mock(spec=EntrezClient)

    @patch('openemory.harvest.entrez.sleep')
    @patch('openemory.harvest.entrez.xmlmap')
    def test_query_set_requests(self, mock_xmlmap, mock_sleep):
        mock_xmlmap.load_xmlobject_from_file.return_value = self.fetch_response
        
        # use query args here from openemory.harvest.models. specific values
        # aren't important for these tests, though: we just want to verify
        # that they get passed to the query.
        qs = ArticleQuerySet(EntrezClient(), results=self.search_response,
                db='pmc', usehistory='y',
                WebEnv=self.search_response.webenv,
                query_key=self.search_response.query_key)
        # creating the queryset doesn't execute any queries
        self.assertEqual(mock_xmlmap.load_xmlobject_from_file.call_count, 0)

        # restrict (slice) the queryset
        s = qs[20:35]
        # this doesn't execute any queries
        self.assertEqual(mock_xmlmap.load_xmlobject_from_file.call_count, 0)

        # request three items from the slice
        objs = s[0], s[5], s[14]
        # this made only a single query
        self.assertEqual(mock_xmlmap.load_xmlobject_from_file.call_count, 1)
        # the query included the initial queryset args
        args, kwargs = mock_xmlmap.load_xmlobject_from_file.call_args
        query_url = args[0]
        self.assertTrue('db=pmc' in query_url)
        self.assertTrue('usehistory=y' in query_url)
        self.assertTrue('WebEnv=' in query_url)
        self.assertTrue('query_key=' in query_url)
        # it also included the correct start/max
        self.assertTrue('retstart=20' in query_url)
        self.assertTrue('retmax=15' in query_url)

        # invalid indexes
        self.assertRaises(IndexError, lambda: s[15])
        self.assertRaises(IndexError, lambda: s[-16])

        # and still just that one call
        self.assertEqual(mock_xmlmap.load_xmlobject_from_file.call_count, 1)

        # making a second slice doesn't make a query
        s = qs[35:50]
        # but getting an item from it does
        obj = s[3]
        self.assertEqual(mock_xmlmap.load_xmlobject_from_file.call_count, 2)
        # this call had the new start/max
        args, kwargs = mock_xmlmap.load_xmlobject_from_file.call_args_list[-1]
        query_url = args[0]
        self.assertTrue('retstart=35' in query_url)
        self.assertTrue('retmax=15' in query_url)

    def test_slicing(self):
        qs = ArticleQuerySet(self.mock_client, results=self.search_response,
                db='pmc', usehistory='y',
                WebEnv=self.search_response.webenv,
                query_key=self.search_response.query_key)

        def check(s, start, stop, msg):
            self.assertEqual(s.start, start, msg + ' (start)')
            self.assertEqual(s.stop, stop, msg + ' (stop)')

        # for easy reference
        check(qs, 0,    7557, 'original query set')

        # basic slices
        check(qs[:],    0,    7557, 'full slice')
        check(qs[20:],  20,   7557, 'positive start')
        check(qs[-20:], 7537, 7557, 'negative start')
        check(qs[:20],  0,    20,   'positive stop')
        check(qs[:-20], 0,    7537, 'negative stop')

        # slices overshooting query bounds
        check(qs[9000:],       7557, 7557, 'large positive start')
        check(qs[-9000:],      0,    7557, 'large negative start')
        check(qs[:9000],       0,    7557, 'large positive stop')
        check(qs[:-9000],      0,    0,    'large negative stop')
        check(qs[6000:5000],   6000, 6000, 'positive start larger than stop')
        check(qs[-5000:-6000], 2557, 2557, 'negative start larger than stop')

        # basic subslices
        check(qs[10:20][:],   10, 20, 'full subslice')
        check(qs[10:20][5:],  15, 20, 'positive subslice start')
        check(qs[10:20][-5:], 15, 20, 'negative subslice start')
        check(qs[10:20][:5],  10, 15, 'positive subslice stop')
        check(qs[10:20][:-5], 10, 15, 'negative subslice stop')

        # subslices overshooting slice bounds
        check(qs[10:20][15:],   20, 20, 'large positive subslice start')
        check(qs[10:20][-15:],  10, 20, 'large negative subslice start')
        check(qs[10:20][:15],   10, 20, 'large positive subslice stop')
        check(qs[10:20][:-15],  10, 10, 'large negative subslice stop')
        check(qs[10:20][7:3],   17, 17, 'positive subslice start larger than stop')
        check(qs[10:20][-3:-7], 17, 17, 'negative subslice start larger than stop')

        # subslices overshooting query bounds
        check(qs[10:20][9000:],  20, 20, 'very large positive subslice start')
        check(qs[10:20][-9000:], 10, 20, 'very large negative subslice start')
        check(qs[10:20][:9000],  10, 20, 'very large positive subslice stop')
        check(qs[10:20][:-9000], 10, 10, 'very large negative subslice stop')


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
    fixtures = ['harvest_authors', 'harvest_records']
    
    def setUp(self):
        article_fixture_path = fixture_path('efetch-retrieval-from-hist.xml')
        self.fetch_response = xmlmap.load_xmlobject_from_file(article_fixture_path,
                                                              xmlclass=EFetchResponse)
        # one corresponding author with an emory email
        self.article = self.fetch_response.articles[0]

    def test_init_from_fetched_article(self):
        # delete corresponding db fixture object so we can reload it
        HarvestRecord.objects.get(pmcid=self.article.docid).delete()
        
        # mock identifiable authors to avoid actual look-up
        with patch.object(self.article, 'identifiable_authors', new=Mock(return_value=[])):
            record = HarvestRecord.init_from_fetched_article(self.article)
            self.assertEqual(self.article.article_title, record.title)
            self.assertEqual(self.article.docid, record.pmcid)
            self.assertEqual(self.article.fulltext_available, record.fulltext)
            self.assertEqual(0, record.authors.count())

            self.assertEqual(self.article.serialize(pretty=True),
                             record.content.read(),
                'article xml should be saved in content file field')
            
            # remove the new record so we can test creating it again
            record.content.delete()
            record.delete()

        # simulate identifiable authors 
        testauthor = User(username='author')
        testauthor.save()
        with patch.object(self.article, 'identifiable_authors',
                          new=Mock(return_value=[testauthor])):
            record = HarvestRecord.init_from_fetched_article(self.article)
            self.assertEqual(1, record.authors.count())
            self.assert_(testauthor in record.authors.all())
            record.content.delete()

    def test_mark_ingested(self):
        record = HarvestRecord.objects.get(pmcid=self.article.docid)
        record.mark_ingested()

        # get a fresh copy from the db
        record = HarvestRecord.objects.get(pmcid=self.article.docid)
        expected, got = 'ingested', record.status,
        self.assertEqual(expected, got,
            'record status should be set to %s by mark_ingested, got %s' % (expected, got))
        self.assertEqual('', record.content.name,
            'article content file should be removed by mark_ingested')

    def test_ingestable(self):
        record = HarvestRecord.objects.get(pmcid=self.article.docid)
        self.assertTrue(record.ingestable)
        record.status = 'ingested'
        self.assertFalse(record.ingestable)
        record.status = 'ignored'
        self.assertFalse(record.ingestable)
        
    def test_as_publication_article(self):
        # fixture with multiple authors
        record = HarvestRecord.objects.get(pmcid=2888474)
        article = record.as_publication_article()

        # test article fields that should be set
        self.assertEqual(record.title, article.label,
            'article title should be set as label')
        self.assertEqual(record.title, article.dc.content.title,
            'article title should be set as dc:title')
        self.assertEqual(record.access_url, article.dc.content.identifier,
            'PubMed Central URL should be set as dc:identifier')
        # this record has two authors; ensure both are listed appropriately
        for author in record.authors.all():
            self.assert_(author.username in article.owner,
                'author username should be included in object owner')
            self.assert_(author.get_full_name() in article.dc.content.creator_list,
                'author full name should be set in dc:creator')

        # contentMetadata content should be the file field on this record
        self.assertEqual(record.content, article.contentMetadata.content)

        self.assertFalse(article.exists,
             'Article object returned should not yet be saved to Fedora')
