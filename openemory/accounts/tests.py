from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpRequest
from django.test import TestCase
from django.contrib.auth.models import User, AnonymousUser
from eulfedora.server import Repository
from eulfedora.util import parse_rdf, RequestFailed
import json
import logging
from mock import Mock, patch, MagicMock
import os
from rdflib.graph import Graph as RdfGraph, Literal, RDF, URIRef
from sunburnt import sunburnt
from taggit.models import Tag

from openemory.accounts.auth import permission_required, login_required
from openemory.accounts.models import researchers_by_interest, Bookmark, \
     pids_by_tag, articles_by_tag, UserProfile
from openemory.accounts.templatetags.tags import tags_for_user
from openemory.publication.models import Article
from openemory.publication.views import ARTICLE_VIEW_FIELDS
from openemory.rdfns import DC, FRBR, FOAF

# re-use pdf fixture from publication app
pdf_filename = os.path.join(settings.BASE_DIR, 'publication', 'fixtures', 'test.pdf')
pdf_md5sum = '331e8397807e65be4f838ccd95787880'

logger = logging.getLogger(__name__)


# credentials for test accounts in json fixture
USER_CREDENTIALS = {
    'staff': {'username': 'staff', 'password': 'GPnFswH9X8'},
    'super': {'username': 'super', 'password': 'awXM6jnwJj'}, 
    'admin': {'username': 'siteadmin', 'password': '8SLEYvF4Tc'},
    
}

def simple_view(request):
    "a simple view for testing custom auth decorators"
    return HttpResponse("Hello, World")

class BasePermissionTestCase(TestCase):
    '''Common setup/teardown functionality for permission_required and
    login_required tests.
    '''
    fixtures =  ['users']

    def setUp(self):
        self.request = HttpRequest()
        self.request.user = AnonymousUser()

        self.ajax_request = HttpRequest()
        self.ajax_request.META['HTTP_X_REQUESTED_WITH'] = 'XMLHttpRequest'
        self.ajax_request.user = AnonymousUser()
        
        self.staff_user = User.objects.get(username='staff')
        self.super_user = User.objects.get(username='super')


class PermissionRequiredTest(BasePermissionTestCase):

    def setUp(self):
        super(PermissionRequiredTest, self).setUp()
        decorator = permission_required('foo.can_edit')
        # decorate simple view above for testing
        self.decorated = decorator(simple_view)

    def test_wraps(self):
        self.assertEqual(simple_view.__doc__, self.decorated.__doc__)
        
    def test_anonymous(self):        
        response = self.decorated(self.request)
        expected, got = 401, response.status_code
        self.assertEqual(expected, got,
                "expected status code %s but got %s for decorated view with non-logged in user" \
                % (expected, got))

        # ajax request
        response = self.decorated(self.ajax_request)
        expected, got = 401, response.status_code
        self.assertEqual(expected, got,
                "expected status code %s but got %s for anonymous ajax request" \
                % (expected, got))
        expected, got = 'text/plain', response['Content-Type']
        self.assertEqual(expected, got,
                "expected content type %s but got %s for anonymous ajax request" \
                % (expected, got))
        expected, got = 'Not Authorized', response.content
        self.assertEqual(expected, got,
                "expected response content %s but got %s for anonymous ajax request" \
                % (expected, got))

    def test_logged_in_notallowed(self):
        # set request to use staff user
        self.request.user = self.staff_user
        response = self.decorated(self.request)
        
        expected, got = 403, response.status_code
        self.assertEqual(expected, got,
                "expected status code %s but got %s for decorated view with logged-in user without perms" \
                % (expected, got))
        self.assert_("Permission Denied" in response.content,
                "response should contain content from 403.html template fixture")

        # ajax request
        self.ajax_request.user = self.staff_user
        response = self.decorated(self.ajax_request)
        expected, got = 403, response.status_code
        self.assertEqual(expected, got,
                "expected status code %s but got %s for ajax request by logged in user without perms" \
                % (expected, got))
        expected, got = 'text/plain', response['Content-Type']
        self.assertEqual(expected, got,
                "expected content type %s but got %s for ajax request by logged in user without perms" \
                % (expected, got))
        expected, got = 'Permission Denied', response.content
        self.assertEqual(expected, got,
                "expected response content %s but got %s for ajax request by logged in user without perms" \
                % (expected, got))


    def test_logged_in_allowed(self):
        # set request to use superuser account
        self.request.user = self.super_user
        response = self.decorated(self.request)
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
                "expected status code %s but got %s for decorated view with superuser" \
                % (expected, got))
        self.assert_("Hello, World" in response.content,
                     "response should contain actual view content")

class LoginRequiredTest(BasePermissionTestCase):

    def setUp(self):
        super(LoginRequiredTest, self).setUp()
        decorator = login_required()
        # decorate simple view above for testing
        self.decorated = decorator(simple_view)

    def test_wraps(self):
        self.assertEqual(simple_view.__doc__, self.decorated.__doc__)
        
    def test_anonymous(self):        
        response = self.decorated(self.request)
        expected, got = 401, response.status_code
        self.assertEqual(expected, got,
                "expected status code %s but got %s for decorated view with non-logged in user" \
                % (expected, got))
        
    def test_logged_in(self):
        # set request to use staff user
        self.request.user = self.staff_user
        response = self.decorated(self.request)
        
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
                "expected status code %s but got %s for decorated view with superuser" \
                % (expected, got))
        self.assert_("Hello, World" in response.content,
                     "response should contain actual view content")


class AccountViewsTest(TestCase):
    fixtures =  ['users']

    def setUp(self):
        self.staff_user = User.objects.get(username='staff')

        self.repo = Repository(username=settings.FEDORA_TEST_USER,
                                     password=settings.FEDORA_TEST_PASSWORD)
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


    mocksolr = Mock(sunburnt.SolrInterface)
    mocksolr.return_value = mocksolr
    # solr interface has a fluent interface where queries and filters
    # return another solr query object; simulate that as simply as possible
    mocksolr.query.return_value = mocksolr.query
    mocksolr.query.query.return_value = mocksolr.query
    mocksolr.query.filter.return_value = mocksolr.query
    mocksolr.query.paginate.return_value = mocksolr.query
    mocksolr.query.exclude.return_value = mocksolr.query
    mocksolr.query.sort_by.return_value = mocksolr.query
    mocksolr.query.field_limit.return_value = mocksolr.query

    @patch('openemory.util.sunburnt.SolrInterface', mocksolr)
    def test_profile(self):
        profile_url = reverse('accounts:profile', kwargs={'username': 'nonuser'})
        response = self.client.get(profile_url)
        expected, got = 404, response.status_code
        self.assertEqual(expected, got, 'Expected %s but got %s for %s (non-existent user)' % \
                         (expected, got, profile_url))
        # mock result object
        result =  [
            {'title': 'article one', 'created': 'today', 'state': 'A',
             'last_modified': 'today', 'pid': 'a:1', 'owner': 'staff',
             'dsids': ['content'], 'parsed_author':
               ['nonuser:A. Non User', ':N. External User']},
            {'title': 'article two', 'created': 'yesterday', 'state': 'A',
             'last_modified': 'today','pid': 'a:2', 'owner': 'staff',
             'dsids': ['contentMetadata'], 'pmcid': '123456', 'parsed_author':
               ['nonuser:A. Non User', 'other:N. Other User']},
        ]
        unpub_result = [
            {'title': 'upload.pdf', 'created': 'today', 'state': 'I',
             'last_modified': 'today', 'pid': 'a:3', 'owner': 'staff'}
            ]
        
        profile_url = reverse('accounts:profile', kwargs={'username': 'staff'})
        with patch('openemory.accounts.views.get_object_or_404') as mockgetobj:
            mockgetobj.return_value = self.staff_user
            with patch.object(self.staff_user, 'get_profile') as mock_getprofile:
                mock_getprofile.return_value.recent_articles.return_value = result
                # not logged in as user yet - unpub should not be called
                mock_getprofile.return_value.unpublished_articles.return_value = unpub_result
                response = self.client.get(profile_url)
                mock_getprofile.return_value.recent_articles.assert_called_once()
                mock_getprofile.return_value.unpublished_articles.assert_not_called()
            
                self.assertContains(response, self.staff_user.get_full_name(),
                    msg_prefix="profile page should display user's display name")
                self.assertContains(response, result[0]['title'],
                    msg_prefix='profile page should display article title')
                self.assertContains(response, result[0]['created'])
                self.assertContains(response, result[0]['last_modified'])
                self.assertContains(response, result[1]['title'])
                self.assertContains(response, result[1]['created'])
                self.assertContains(response, result[1]['last_modified'])
                # first result has content datastream, should have pdf link
                self.assertContains(response,
                                    reverse('publication:pdf', kwargs={'pid': result[0]['pid']}),
                                    msg_prefix='profile should link to pdf for article')
                # first result coauthored with a non-emory author
                coauthor_name = result[0]['parsed_author'][1].partition(':')[2]
                self.assertContains(response, coauthor_name,
                                    msg_prefix='profile should include non-emory coauthor')
                # second result does not have content datastream, should NOT have pdf link
                self.assertNotContains(response,
                                    reverse('publication:pdf', kwargs={'pid': result[1]['pid']}),
                                    msg_prefix='profile should link to pdf for article')

                # second result DOES have pmcid, should have pubmed central link
                self.assertNotContains(response,
                                    reverse('publication:pdf', kwargs={'pid': result[1]['pid']}),
                                    msg_prefix='profile should link to pdf for article')
                # second result coauthored with an emory author
                coauthor = result[1]['parsed_author'][1]
                coauthor_netid, colon, coauthor_name = coauthor.partition(':')
                self.assertContains(response, coauthor_name,
                                    msg_prefix='profile should include emory coauthor name')
                self.assertContains(response,
                                    reverse('accounts:profile', kwargs={'username': coauthor_netid}),
                                    msg_prefix='profile should link to emory coauthor')


                # normally, no upload link should be shown on profile page
                self.assertNotContains(response, reverse('publication:ingest'),
                    msg_prefix='profile page upload link should not display to anonymous user')

                # no research interests
                self.assertNotContains(response, 'Research interests',
                    msg_prefix='profile page should not display "Research interests" when none are set')

                
        # add research interests
        tags = ['myopia', 'arachnids', 'climatology']
        self.staff_user.get_profile().research_interests.add(*tags)
        response = self.client.get(profile_url)
        self.assertContains(response, 'Research interests',
            msg_prefix='profile page should not display "Research interests" when tags are set')
        for tag in tags:
            self.assertContains(response, tag,
                msg_prefix='profile page should display research interest tags')

        # logged in, looking at own profile
        self.client.login(**USER_CREDENTIALS['staff'])
        with patch('openemory.accounts.views.get_object_or_404') as mockgetobj:
            mockgetobj.return_value = self.staff_user
            with patch.object(self.staff_user, 'get_profile') as mock_getprofile:
                mock_getprofile.return_value.recent_articles.return_value = result
                # not logged in as user yet - unpub should not be called
                mock_getprofile.return_value.unpublished_articles.return_value = unpub_result
                mock_getprofile.return_value.research_interests.all.return_value = []
                response = self.client.get(profile_url)
                mock_getprofile.return_value.recent_articles.assert_called_once()
                mock_getprofile.return_value.unpublished_articles.assert_called_once()

                self.assertContains(response, reverse('publication:ingest'),
                    msg_prefix='user looking at their own profile page should see upload link')
                # tag editing enabled
                self.assertTrue(response.context['editable_tags'])
                self.assert_('tagform' in response.context)
                # unpublished articles
                self.assertContains(response, 'You have unpublished articles',
                    msg_prefix='user with unpublished articles should see them on their own profile page')
                self.assertContains(response, unpub_result[0]['title'])
                self.assertContains(response, reverse('publication:edit',
                                                      kwargs={'pid': unpub_result[0]['pid']}),
                    msg_prefix='profile should include edit link for unpublished article')
                self.assertNotContains(response, reverse('publication:edit',
                                                      kwargs={'pid': result[0]['pid']}),
                    msg_prefix='profile should not include edit link for published article')
                
        # logged in, looking at someone else's profile
        profile_url = reverse('accounts:profile', kwargs={'username': 'super'})
        response = self.client.get(profile_url)
        self.assertNotContains(response, reverse('publication:ingest'),
            msg_prefix='logged-in user looking at another profile page should not see upload link')
        # tag editing not enabled
        self.assert_('editable_tags' not in response.context)
        self.assert_('tagform' not in response.context)
                
        # personal bookmarks
        bk, created = Bookmark.objects.get_or_create(user=self.staff_user, pid=result[0]['pid'])
        super_tags = ['new', 'to read']
        bk.tags.set(*super_tags)
        response = self.client.get(profile_url)
        for tag in super_tags:
            self.assertContains(response, tag,
                 msg_prefix='user sees their private article tags in any article list view')
        

    @patch('openemory.util.sunburnt.SolrInterface', mocksolr)
    def test_profile_rdf(self):
        # mock solr result 
        result =  [
            {'title': 'article one', 'created': 'today',
             'last_modified': 'today', 'pid': self.article.pid},
        ]
        self.mocksolr.query.execute.return_value = result

        profile_url = reverse('accounts:profile', kwargs={'username': 'staff'})
        profile_uri = URIRef('http://testserver' + profile_url)
        response = self.client.get(profile_url, HTTP_ACCEPT='application/rdf+xml')
        self.assertEqual('application/rdf+xml', response['Content-Type'])

        location_url = reverse('accounts:profile-data', kwargs={'username': 'staff'})
        location_uri = 'http://testserver' + location_url
        self.assertEqual(location_uri, response['Content-Location'])
        self.assertTrue('Accept' in response['Vary'])

        # check that content parses with rdflib, check a few triples
        rdf = parse_rdf(response.content, profile_url)
        self.assert_(isinstance(rdf, RdfGraph))
        topics = list(rdf.objects(profile_uri, FOAF.primaryTopic))
        self.assertTrue(topics, 'page should have a foaf:primaryTopic')
        author_node = topics[0]
        self.assert_( (author_node, RDF.type, FOAF.Person)
                      in rdf,
                      'author should be set as a foaf:Person in profile rdf')
        self.assertEqual(URIRef(self.staff_user.get_full_name()),
                         rdf.value(subject=author_node, predicate=FOAF.name),
                      'author full name should be set as a foaf:name in profile rdf')
        self.assertEqual(URIRef('http://testserver' + profile_url),
                         rdf.value(subject=author_node, predicate=FOAF.publications),
                      'author profile url should be set as a foaf:publications in profile rdf')
        # test article rdf included, related
        article_nodes = list(rdf.subjects(DC.identifier, Literal(self.article.pid)))
        self.assertEqual(len(article_nodes), 1, 'one article should have reposited pid')
        article_node = article_nodes[0]
        self.assert_((author_node, FRBR.creatorOf, article_node)
                     in rdf,
                     'author should be set as a frbr:creatorOf article in profile rdf')
        self.assert_((author_node, FOAF.made, article_node)
                     in rdf,
                     'author should be set as a foaf:made article in profile rdf')
        
        for triple in self.article.as_rdf(node=article_node):
            self.assert_(triple in rdf,
                         'article rdf should be included in profile rdf graph')

    def test_login(self):
        login_url = reverse('accounts:login')
        # without next - wrong password should redirect to site index
        response = self.client.post(login_url, {'username': 'staff', 'password': 'wrong'})
        expected, got = 303, response.status_code
        self.assertEqual(expected, got, 'Expected %s but got %s for failed login on %s' % \
                         (expected, got, login_url))
        self.assertEqual('http://testserver' + reverse('site-index'),
                         response['Location'],
                         'failed login with no next url should redirect to site index')
        # with next - wrong password should redirect to next
        response = self.client.post(login_url, {'username': 'staff', 'password': 'wrong',
                                                'next': reverse('publication:ingest')})
        expected, got = 303, response.status_code
        self.assertEqual(expected, got, 'Expected %s but got %s for failed login on %s' % \
                         (expected, got, login_url))
        self.assertEqual('http://testserver' + reverse('publication:ingest'),
                         response['Location'],
                         'failed login should redirect to next url when it is specified')

        # login with valid credentials but no next
        response = self.client.post(login_url, USER_CREDENTIALS['staff'])
        expected, got = 303, response.status_code
        self.assertEqual(expected, got, 'Expected %s but got %s for successful login on %s' % \
                         (expected, got, login_url))
        self.assertEqual('http://testserver' +
                         reverse('accounts:profile', kwargs={'username': 'staff'}),
                         response['Location'],
                         'successful login with no next url should redirect to user profile')


        # login with valid credentials and no next, user in Site Admin group
        response = self.client.post(login_url, USER_CREDENTIALS['admin'])
        expected, got = 303, response.status_code
        self.assertEqual(expected, got, 'Expected %s but got %s for successful login on %s' % \
                         (expected, got, login_url))
        self.assertEqual('http://testserver' + reverse('harvest:queue'),
                         response['Location'],
                         'successful admin login with no next url should redirect to harvest queue')

        # login with valid credentials and a next url specified
        opts = {'next': reverse('site-index')}
        opts.update(USER_CREDENTIALS['staff'])
        response = self.client.post(login_url, opts)
        expected, got = 302, response.status_code
        self.assertEqual(expected, got, 'Expected %s but got %s for successful login on %s' % \
                         (expected, got, login_url))
        self.assertEqual('http://testserver' + opts['next'],
                         response['Location'],
                         'successful login should redirect to next url when specified')


        # site-index login form should not specify 'next'
        self.client.logout()
        response = self.client.get(reverse('site-index'))
        self.assertNotContains(response, '<input type=hidden name=next',
            msg_prefix='login-form on site index page should not specify a next url')

    def test_tag_profile_GET(self):
        # add some tags to a user profile to fetch
        user = User.objects.get(username=USER_CREDENTIALS['staff']['username'])
        tags = ['a', 'b', 'c', 'z']
        user.get_profile().research_interests.set(*tags)
        
        tag_profile_url = reverse('accounts:profile-tags',
                                  kwargs={'username': USER_CREDENTIALS['staff']['username']})
        response = self.client.get(tag_profile_url)
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for GET on %s' % \
                         (expected, got, tag_profile_url))
        # inspect return response
        self.assertEqual('application/json', response['Content-Type'],
             'should return json on success')
        data = json.loads(response.content)
        self.assert_(data, "Response content successfully read as JSON")
        for tag in tags:
            self.assert_(tag in data)
            self.assertEqual(reverse('accounts:by-interest', kwargs={'tag': tag}),
                             data[tag])

        # check (currently) unsupported HTTP methods
        response = self.client.delete(tag_profile_url)
        expected, got = 405, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s (method not allowed) but got %s for DELETE on %s' % \
                         (expected, got, tag_profile_url))

        # bogus username - 404
        bogus_tag_profile_url = reverse('accounts:profile-tags',
                                  kwargs={'username': 'adumbledore'})
        response = self.client.get(bogus_tag_profile_url)
        expected, got = 404, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for GET on %s (bogus username)' % \
                         (expected, got, bogus_tag_profile_url))


    def test_tag_profile_PUT(self):
        tag_profile_url = reverse('accounts:profile-tags',
                                  kwargs={'username': USER_CREDENTIALS['staff']['username']})

        # attempt to set tags without being logged in
        response = self.client.put(tag_profile_url, data='one, two, three',
                                   content_type='text/plain')
        expected, got = 401, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for PUT on %s as AnonymousUser' % \
                         (expected, got, tag_profile_url))

        # login as different user than the one being tagged
        self.client.login(**USER_CREDENTIALS['admin'])
        response = self.client.put(tag_profile_url, data='one, two, three',
                                   content_type='text/plain')
        expected, got = 403, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for PUT on %s as different user' % \
                         (expected, got, tag_profile_url))
        
        # login as user being tagged
        self.client.login(**USER_CREDENTIALS['staff'])
        tags = ['one', '2', 'three four', 'five']
        response = self.client.put(tag_profile_url, data=', '.join(tags),
                                   content_type='text/plain')
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for PUT on %s as user' % \
                         (expected, got, tag_profile_url))
        # inspect return response
        self.assertEqual('application/json', response['Content-Type'],
             'should return json on success')
        data = json.loads(response.content)
        self.assert_(data, "Response content successfully read as JSON")
        for tag in tags:
            self.assert_(tag in data)

        # inspect user in db
        user = User.objects.get(username=USER_CREDENTIALS['staff']['username'])
        for tag in tags:
            self.assertTrue(user.get_profile().research_interests.filter(name=tag).exists())

    def test_tag_profile_POST(self):
        tag_profile_url = reverse('accounts:profile-tags',
                                  kwargs={'username': USER_CREDENTIALS['staff']['username']})

        # attempt to set tags without being logged in
        response = self.client.post(tag_profile_url, data='one, two, three',
                                   content_type='text/plain')
        expected, got = 401, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for POST on %s as AnonymousUser' % \
                         (expected, got, tag_profile_url))

        # login as different user than the one being tagged
        self.client.login(**USER_CREDENTIALS['admin'])
        response = self.client.post(tag_profile_url, data='one, two, three',
                                   content_type='text/plain')
        expected, got = 403, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for POST on %s as different user' % \
                         (expected, got, tag_profile_url))
        
        # login as user being tagged
        self.client.login(**USER_CREDENTIALS['staff'])
        # add initial tags to user
        initial_tags = ['one', '2']
        self.staff_user.get_profile().research_interests.add(*initial_tags)
        new_tags = ['three four', 'five', '2']  # duplicate tag should be fine too
        response = self.client.post(tag_profile_url, data=', '.join(new_tags),
                                   content_type='text/plain')
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for POST on %s as user' % \
                         (expected, got, tag_profile_url))
        # inspect return response
        self.assertEqual('application/json', response['Content-Type'],
             'should return json on success')
        data = json.loads(response.content)
        self.assert_(data, "Response content successfully read as JSON")
        for tag in initial_tags:
            self.assert_(tag in data, 'initial tags should be set and returned on POST')
        for tag in new_tags:
            self.assert_(tag in data, 'new tags should be added and returned on POST')

        # inspect user in db
        user = User.objects.get(username=USER_CREDENTIALS['staff']['username'])
        for tag in initial_tags:
            self.assertTrue(user.get_profile().research_interests.filter(name=tag).exists())
        for tag in new_tags:
            self.assertTrue(user.get_profile().research_interests.filter(name=tag).exists())

    @patch('openemory.accounts.models.solr_interface', mocksolr)
    def test_profiles_by_interest(self):
        mock_article = {'pid': 'article:1', 'title': 'mock article'}
        self.mocksolr.query.execute.return_value = [mock_article]
        
        # add tags
        oa = 'open-access'
        oa_scholar, created = User.objects.get_or_create(username='oascholar')
        self.staff_user.get_profile().research_interests.add('open access', 'faculty habits')
        oa_scholar.get_profile().research_interests.add('open access', 'OA movement')

        prof_by_tag_url = reverse('accounts:by-interest', kwargs={'tag': oa})
        response = self.client.get(prof_by_tag_url)
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for %s' % \
                         (expected, got, prof_by_tag_url))
        # check response
        oa_tag = Tag.objects.get(slug=oa)
        self.assertEqual(oa_tag, response.context['interest'],
            'research interest tag should be passed to template context for display')
        self.assertContains(response, self.staff_user.get_profile().get_full_name(),
            msg_prefix='response should display full name for users with specified interest')
        self.assertContains(response, oa_scholar.get_profile().get_full_name(),
            msg_prefix='response should display full name for users with specified interest')
        for tag in self.staff_user.get_profile().research_interests.all():
            self.assertContains(response, tag.name,
                 msg_prefix='response should display other tags for users with specified interest')
            self.assertContains(response,
                 reverse('accounts:by-interest', kwargs={'tag': tag.slug}),
                 msg_prefix='response should link to other tags for users with specified interest')
        self.assertContains(response, mock_article['title'],
             msg_prefix='response should include recent article titles for matching users')

        # not logged in - no me too / you have this interest
        self.assertNotContains(response, 'one of your research interests',
            msg_prefix='anonymous user should not see indication they have this research interest')
        self.assertNotContains(response, 'add to my profile',
            msg_prefix='anonymous user should not see option to add this research interest to profile')

        # logged in, with this interest: should see indication 
        self.client.login(**USER_CREDENTIALS['staff'])
        response = self.client.get(prof_by_tag_url)
        self.assertContains(response, 'one of your research interests', 
            msg_prefix='logged in user with this interest should see indication')
        
        self.staff_user.get_profile().research_interests.clear()
        response = self.client.get(prof_by_tag_url)
        self.assertContains(response, 'add to my profile', 
            msg_prefix='logged in user without this interest should have option to add to profile')

    def test_interests_autocomplete(self):
        # create some users with tags to search on
        testuser1, created = User.objects.get_or_create(username='testuser1')
        testuser1.get_profile().research_interests.add('Chemistry', 'Biology', 'Microbiology')
        testuser2, created = User.objects.get_or_create(username='testuser2')
        testuser2.get_profile().research_interests.add('Chemistry', 'Geology', 'Biology')
        testuser3, created = User.objects.get_or_create(username='testuser3')
        testuser3.get_profile().research_interests.add('Chemistry', 'Kinesiology')

        # bookmark tags should *not* count towards public tags
        bk1, new = Bookmark.objects.get_or_create(user=testuser1, pid='test:1')
        bk1.tags.set('Chemistry', 'to-read')

        interests_autocomplete_url = reverse('accounts:interests-autocomplete')
        response = self.client.get(interests_autocomplete_url, {'s': 'chem'})
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for %s' % \
                         (expected, got, interests_autocomplete_url))
        # inspect return response
        self.assertEqual('application/json', response['Content-Type'],
             'should return json on success')
        data = json.loads(response.content)
        self.assert_(data, "Response content successfully read as JSON")
        self.assertEqual('Chemistry', data[0]['value'],
            'response includes matching tag')
        self.assertEqual('Chemistry (3)', data[0]['label'],
            'display label includes correct term count')

        response = self.client.get(interests_autocomplete_url, {'s': 'BIO'})
        data = json.loads(response.content)
        self.assertEqual('Biology', data[0]['value'],
            'response includes matching tag (case-insensitive match)')
        self.assertEqual('Biology (2)', data[0]['label'],
            'response includes term count (most used first)')
        self.assertEqual('Microbiology', data[1]['value'],
            'response includes partially matching tag (internal match)')
        self.assertEqual('Microbiology (1)', data[1]['label'])

        # private bookmark tag should not be returned
        response = self.client.get(interests_autocomplete_url, {'s': 'read'})
        data = json.loads(response.content)
        self.assertEqual([], data)

    def test_tag_object_GET(self):
        # create a bookmark to get
        bk, created = Bookmark.objects.get_or_create(user=self.staff_user, pid='pid:test1')
        mytags = ['nasty', 'brutish', 'short']
        bk.tags.set(*mytags)
        tags_url = reverse('accounts:tags', kwargs={'pid': bk.pid})

        # not logged in - forbidden
        response = self.client.get(tags_url)
        expected, got = 401, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for GET on %s (not logged in)' % \
                         (expected, got, tags_url))

        # log in for subsequent tests
        self.client.login(**USER_CREDENTIALS['staff'])

        # untagged pid - 404
        untagged_url = reverse('accounts:tags', kwargs={'pid': 'pid:notags'})
        response = self.client.get(untagged_url)
        expected, got = 404, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for GET on %s' % \
                         (expected, got, untagged_url))
        
        # logged in, get tagged pid
        response = self.client.get(tags_url)
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for GET on %s' % \
                         (expected, got, tags_url))
        # inspect return response
        self.assertEqual('application/json', response['Content-Type'],
                         'should return json on success')
        data = json.loads(response.content)
        self.assert_(isinstance(data, list), "Response content successfully read as JSON")
        for tag in mytags:
            self.assert_(tag in data)
        
        # check currently unsupported HTTP methods
        response = self.client.delete(tags_url)
        expected, got = 405, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s (method not allowed) but got %s for DELETE on %s' % \
                         (expected, got, tags_url))
        response = self.client.post(tags_url)
        expected, got = 405, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s (method not allowed) but got %s for POST on %s' % \
                         (expected, got, tags_url))


    @patch('openemory.accounts.views.Repository')
    def test_tag_object_PUT(self, mockrepo):
        # use mock repo to simulate an existing fedora object 
        mockrepo.return_value.get_object.return_value.exists = True
        
        testpid = 'pid:bk1'
        tags_url = reverse('accounts:tags', kwargs={'pid': testpid})
        mytags = ['pleasant', 'nice', 'long']
        
        # attempt to set tags without being logged in
        response = self.client.put(tags_url, data=', '.join(mytags),
                                   content_type='text/plain')
        expected, got = 401, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for PUT on %s as AnonymousUser' % \
                         (expected, got, tags_url))
        
        # log in for subsequent tests
        self.client.login(**USER_CREDENTIALS['staff'])
        # create a new bookmark
        response = self.client.put(tags_url, data=', '.join(mytags),
                                   content_type='text/plain')
        expected, got = 201, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for PUT on %s (logged in, new bookmark)' % \
                         (expected, got, tags_url))
        
        # inspect return response
        self.assertEqual('application/json', response['Content-Type'],
                         'should return json on success')
        data = json.loads(response.content)
        self.assert_(isinstance(data, list), "Response content successfully read as JSON")
        for tag in mytags:
            self.assert_(tag in data)

        # inspect bookmark in db
        self.assertTrue(Bookmark.objects.filter(user=self.staff_user, pid=testpid).exists())
        bk = Bookmark.objects.get(user=self.staff_user, pid=testpid)
        for tag in mytags:
            self.assertTrue(bk.tags.filter(name=tag).exists())

        # update same bookmark with a second put
        response = self.client.put(tags_url, data=', '.join(mytags[:2]),
                                   content_type='text/plain')
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for PUT on %s (logged in, existing bookmark)' % \
                         (expected, got, tags_url))
        data = json.loads(response.content)
        self.assert_(mytags[-1] not in data)
        # get fresh copy of the bookmark
        bk = Bookmark.objects.get(user=self.staff_user, pid=testpid)
        self.assertFalse(bk.tags.filter(name=mytags[-1]).exists())
        
        # test bookmarking when the fedora object doesn't exist
        mockrepo.return_value.get_object.return_value.exists = False
        response = self.client.put(tags_url, data=', '.join(mytags),
                                   content_type='text/plain')
        expected, got = 404, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for PUT on %s (non-existent fedora object)' % \
                         (expected, got, tags_url))

    def test_tag_autocomplete(self):
        # create some bookmarks with tags to search on
        bk1, new = Bookmark.objects.get_or_create(user=self.staff_user, pid='test:1')
        bk1.tags.set('foo', 'bar', 'baz')
        bk2, new = Bookmark.objects.get_or_create(user=self.staff_user, pid='test:2')
        bk2.tags.set('foo', 'bar')
        bk3, new = Bookmark.objects.get_or_create(user=self.staff_user, pid='test:3')
        bk3.tags.set('foo')

        super_user = User.objects.get(username='super')
        bks1, new = Bookmark.objects.get_or_create(user=super_user, pid='test:1')
        bks1.tags.set('foo', 'bar')
        bks2, new = Bookmark.objects.get_or_create(user=super_user, pid='test:2')
        bks2.tags.set('foo')

        tag_autocomplete_url = reverse('accounts:tags-autocomplete')

        # not logged in - 401
        response = self.client.get(tag_autocomplete_url, {'s': 'foo'})
        expected, got = 401, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for %s (not logged in)' % \
                         (expected, got, tag_autocomplete_url))

        self.client.login(**USER_CREDENTIALS['staff'])
        response = self.client.get(tag_autocomplete_url, {'s': 'foo'})
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for %s' % \
                         (expected, got, tag_autocomplete_url))
        data = json.loads(response.content)
        # check return response
        self.assertEqual('foo', data[0]['value'],
            'response includes matching tag')
        # staff user has 3 foo tags
        self.assertEqual('foo (3)', data[0]['label'],
            'display label includes count for current user')

        # login as different user - should get count for their own bookmarks only
        self.client.login(**USER_CREDENTIALS['super'])
        response = self.client.get(tag_autocomplete_url, {'s': 'foo'})
        data = json.loads(response.content)
        # super user has 2 foo tags
        self.assertEqual('foo (2)', data[0]['label'],
            'display label includes correct term count')


    def test_tags_in_sidebar(self):
        # create some bookmarks with tags to search on
        bk1, new = Bookmark.objects.get_or_create(user=self.staff_user, pid='test:1')
        bk1.tags.set('full text', 'to read')
        bk2, new = Bookmark.objects.get_or_create(user=self.staff_user, pid='test:2')
        bk2.tags.set('to read')

        profile = self.staff_user.get_profile()
        profile.research_interests.set('ponies')
        profile.save()

        # can really test any page for this...
        profile_url = reverse('accounts:profile', kwargs={'username': 'staff'})

        # not logged in - no tags in sidebar
        response = self.client.get(profile_url)
        self.assertFalse(response.context['tags'],
            'no tags should be set in response context for unauthenticated user')
        self.assertNotContains(response, '<h2>Tags</h2>',
             msg_prefix='tags should not be displayed in sidebar for unauthenticated user')

        # log in to see tags
        self.client.login(**USER_CREDENTIALS['staff'])
        response = self.client.get(profile_url)
        # tags should be set in context, with count & sorted by count
        tags = response.context['tags']
        self.assertEqual(2, tags.count())
        self.assertEqual('to read', tags[0].name)
        self.assertEqual(2, tags[0].count)
        self.assertEqual('full text', tags[1].name)
        self.assertEqual(1, tags[1].count)
        self.assertContains(response, '<h2>Tags</h2>',
            msg_prefix='tags should not be displayed in sidebar for authenticated user')
        # test for tag-browse urls once they are added
        

    @patch('openemory.accounts.views.articles_by_tag')
    def test_tagged_items(self, mockart_by_tag):
        # create some bookmarks with tags to search on
        bk1, new = Bookmark.objects.get_or_create(user=self.staff_user, pid='test:1')
        bk1.tags.set('full text', 'to read')
        bk2, new = Bookmark.objects.get_or_create(user=self.staff_user, pid='test:2')
        bk2.tags.set('to read')

        tagged_item_url = reverse('accounts:tag', kwargs={'tag': 'to-read'})

        # not logged in - no access
        response = self.client.get(tagged_item_url)
        expected, got = 401, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for %s (not logged in)' % \
                         (expected, got, tagged_item_url))
        
        # log in to see tagged items
        self.client.login(**USER_CREDENTIALS['staff'])
        mockart_by_tag.return_value = [
            {'title': 'test article 1', 'pid': 'test:1'},
            {'title': 'test article 2', 'pid': 'test:2'}
        ]
        response = self.client.get(tagged_item_url)
        # check mock solr response, response display
        mockart_by_tag.assert_called_with(self.staff_user, bk2.tags.all()[0])
        self.assertContains(response, 'Tag: to read',
            msg_prefix='response is labeled by the requested tag')      
        self.assertContains(response, mockart_by_tag.return_value[0]['title'])
        self.assertContains(response, mockart_by_tag.return_value[1]['title'])
        self.assertContains(response, '2 articles',
            msg_prefix='response includes total number of articles')      
        
        # bogus tag - 404
        tagged_item_url = reverse('accounts:tag', kwargs={'tag': 'not-a-real-tag'})
        response = self.client.get(tagged_item_url)
        expected, got = 404, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for %s (nonexistent tag)' % \
                         (expected, got, tagged_item_url))

    @patch('openemory.accounts.views.EmoryLDAPBackend')
    def test_user_names(self, mockldap):
        username_url = reverse('accounts:user-name', kwargs={'username': 'staff'})

        response = self.client.get(username_url, {'username': 'staff'})
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for %s' % \
                         (expected, got, username_url))
        expected, got = 'application/json', response['Content-Type']
        self.assertEqual(expected, got,
                         'Expected content-type %s but got %s for %s' % \
                         (expected, got, username_url))
        data = json.loads(response.content)
        self.assert_(data, "Response content successfully read as JSON")
        self.assertEqual('staff', data['username'])
        self.assertEqual(self.staff_user.last_name, data['last_name'])
        self.assertEqual(self.staff_user.first_name, data['first_name'])
        # ldap should not be called when user is already in db
        mockldap.return_value.find_user.assert_not_called

        # unsupported http method
        response = self.client.delete(username_url)
        expected, got = 405, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s (method not allowed) but got %s for DELETE %s' % \
                         (expected, got, username_url))

        # post again with user not in db - should query ldap
        superuser = User.objects.get(username='super')
        mockldap.return_value.find_user.return_value = ('userdn', superuser)
        username_url = reverse('accounts:user-name', kwargs={'username': 'someotheruser'})
        response = self.client.get(username_url)
        mockldap.return_value.find_user.assert_called
        data = json.loads(response.content)
        self.assert_(data, "Response content successfully read as JSON")
        self.assertEqual(superuser.last_name, data['last_name'])
        self.assertEqual(superuser.first_name, data['first_name'])

        # not found in db or ldap - 404
        mockldap.return_value.find_user.return_value = ('userdn', None)
        response = self.client.get(username_url)
        expected, got = 404, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for %s (user not found in db or ldap)' % \
                         (expected, got, username_url))        
        
class ResarchersByInterestTestCase(TestCase):

    def test_researchers_by_interest(self):
        # no users, no tags
        self.assertEqual(0, researchers_by_interest('chemistry').count())

        # users, no tags
        u1 = User(username='foo')
        u1.save()
        u2 = User(username='bar')
        u2.save()
        u3 = User(username='baz')
        u3.save()
        
        self.assertEqual(0, researchers_by_interest('chemistry').count())

        # users with tags
        u1.get_profile().research_interests.add('chemistry', 'geology', 'biology')
        u2.get_profile().research_interests.add('chemistry', 'biology', 'microbiology')
        u3.get_profile().research_interests.add('chemistry', 'physiology')

        # check various combinations - all users, some, one, none
        chem = researchers_by_interest('chemistry')
        self.assertEqual(3, chem.count())
        for u in [u1, u2, u3]:
            self.assert_(u in chem)

        bio = researchers_by_interest('biology')
        self.assertEqual(2, bio.count())
        for u in [u1, u2]:
            self.assert_(u in bio)

        microbio = researchers_by_interest('microbiology')
        self.assertEqual(1, microbio.count())
        self.assert_(u2 in microbio)
        
        physio = researchers_by_interest('physiology')
        self.assertEqual(1, physio.count())
        self.assert_(u3 in physio)

        psych = researchers_by_interest('psychology')
        self.assertEqual(0, psych.count())

        # also allows searching by tag slug
        chem = researchers_by_interest(slug='chemistry')
        self.assertEqual(3, chem.count())
        
    
class UserProfileTest(TestCase):
    mocksolr = Mock(sunburnt.SolrInterface)
    mocksolr.return_value = mocksolr
    # solr interface has a fluent interface where queries and filters
    # return another solr query object; simulate that as simply as possible
    mocksolr.query.return_value = mocksolr.query
    mocksolr.query.query.return_value = mocksolr.query
    mocksolr.query.filter.return_value = mocksolr.query
    mocksolr.query.paginate.return_value = mocksolr.query
    mocksolr.query.exclude.return_value = mocksolr.query
    mocksolr.query.sort_by.return_value = mocksolr.query
    mocksolr.query.field_limit.return_value = mocksolr.query

    def setUp(self):
        self.user, created = User.objects.get_or_create(username='testuser')
        
    @patch('openemory.accounts.models.solr_interface', mocksolr)
    def test_find_articles(self):
        # check important solr query args
        solrq = self.user.get_profile()._find_articles()
        self.mocksolr.query.assert_called_with(owner=self.user.username)
        qfilt = self.mocksolr.query.filter
        qfilt.assert_called_with(content_model=Article.ARTICLE_CONTENT_MODEL)

    @patch('openemory.accounts.models.solr_interface', mocksolr)
    def test_recent_articles(self):
        # check important solr query args
        testlimit = 4
        testresult = [{'pid': 'test:1234'},]
        self.mocksolr.query.execute.return_value = testresult
        recent = self.user.get_profile().recent_articles(limit=testlimit)
        self.assertEqual(recent, testresult)
        self.mocksolr.query.filter.assert_called_with(state='A')
        self.mocksolr.query.paginate.assert_called_with(rows=testlimit)
        self.mocksolr.query.execute.assert_called_once()

    @patch('openemory.accounts.models.solr_interface', mocksolr)
    def test_unpublished_articles(self):
        # check important solr query args
        unpub = self.user.get_profile().unpublished_articles()
        self.mocksolr.query.filter.assert_called_with(state='I')
        self.mocksolr.query.execute.assert_called_once()

class TagsTemplateFilterTest(TestCase):
    fixtures =  ['users']

    def setUp(self):
        self.staff_user = User.objects.get(username='staff')
        testpid = 'foo:1'
        self.solr_return = {'pid': testpid}
        repo = Repository()
        self.obj = repo.get_object(pid=testpid)

    def test_anonymous(self):
        # anonymous - no error, no tags
        self.assertEqual([], tags_for_user(self.solr_return, AnonymousUser()))

    def test_no_bookmark(self):
        # should not error
        self.assertEqual([], tags_for_user(self.solr_return, self.staff_user))

    def test_bookmark(self):
        # create a bookmark to query
        bk, created = Bookmark.objects.get_or_create(user=self.staff_user,
                                                     pid=self.obj.pid)
        mytags = ['ay', 'bee', 'cee']
        bk.tags.set(*mytags)

        # query for tags by solr return
        tags = tags_for_user(self.solr_return, self.staff_user)
        self.assertEqual(len(mytags), len(tags))
        self.assert_(isinstance(tags[0], Tag))
        tag_names = [t.name for t in tags]
        for tag in mytags:
            self.assert_(tag in tag_names)

        # query for tags by object - should be same
        obj_tags = tags_for_user(self.obj, self.staff_user)
        self.assert_(all(t in obj_tags for t in tags))


    def test_no_pid(self):
        # passing in an object without a pid shouldn't error either
        self.assertEqual([], tags_for_user({}, self.staff_user))
       

class ArticlesByTagTest(TestCase):

    # FIXME: mocksolr duplication ... how to make re-usable/sharable?
    mocksolr = MagicMock(sunburnt.SolrInterface)
    mocksolr.return_value = mocksolr
    # solr interface has a fluent interface where queries and filters
    # return another solr query object; simulate that as simply as possible
    mocksolr.query.return_value = mocksolr.query
    mocksolr.query.query.return_value = mocksolr.query
    mocksolr.query.filter.return_value = mocksolr.query
    mocksolr.query.paginate.return_value = mocksolr.query
    mocksolr.query.exclude.return_value = mocksolr.query
    mocksolr.query.sort_by.return_value = mocksolr.query
    mocksolr.query.field_limit.return_value = mocksolr.query

    def setUp(self):
        self.user, created = User.objects.get_or_create(username='testuser')
        self.testpids = ['test:1', 'test:2', 'test:3']
        tagval = 'test'
        for pid in self.testpids:
            bk, new = Bookmark.objects.get_or_create(user=self.user, pid=pid)
            bk.tags.set(tagval)
            
        self.tag = bk.tags.all()[0]

    def test_pids_by_tag(self):
        tagpids = pids_by_tag(self.user, self.tag)
        self.assertEqual(len(self.testpids), len(tagpids))
        for pid in self.testpids:
            self.assert_(pid in tagpids)

    @patch('openemory.accounts.models.solr_interface', mocksolr)
    def test_articles_by_tag(self):
        articles = articles_by_tag(self.user, self.tag)

        # inspect solr query options
        # Q should be called once for each pid
        q_call_args =self.mocksolr.Q.call_args_list  # list of arg, kwarg tuples
        for i in range(2):
            args, kwargs = q_call_args[i]
            self.assertEqual({'pid': self.testpids[i]}, kwargs)
        self.mocksolr.query.field_limit.assert_called_with(ARTICLE_VIEW_FIELDS)
        self.mocksolr.query.sort_by.assert_called_with('-last_modified')

        # no match should return empty list, not all articles
        t = Tag(name='not tagged')
        self.assertEqual([], articles_by_tag(self.user, t))
        
        
