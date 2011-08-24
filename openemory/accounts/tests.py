from django.conf import settings
from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpRequest
from django.test import TestCase
from django.contrib.auth.models import User, AnonymousUser
from mock import Mock, patch
from sunburnt import sunburnt

from openemory.accounts.auth import permission_required, login_required
from openemory.publication.models import Article


# credentials for test accounts in json fixture
USER_CREDENTIALS = {
    'staff': {'username': 'staff', 'password': 'just4p30n'}, # (just a peon)
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

    @patch('openemory.accounts.views.sunburnt.SolrInterface', mocksolr)
    def test_profile(self):
        profile_url = reverse('accounts:profile', kwargs={'username': 'nonuser'})
        response = self.client.get(profile_url)
        expected, got = 404, response.status_code
        self.assertEqual(expected, got, 'Expected %s but got %s for %s (non-existent user)' % \
                         (expected, got, profile_url))

        # mock result object
        result =  [
            {'title': 'article one', 'created': 'today',
             'last_modified': 'today', 'pid': 'a:1'},
            {'title': 'article two', 'created': 'yesterday',
             'last_modified': 'today','pid': 'a:2'},
        ]
        self.mocksolr.query.execute.return_value = result
        profile_url = reverse('accounts:profile', kwargs={'username': 'staff'})
        response = self.client.get(profile_url)
        self.assertContains(response, self.staff_user.get_full_name(),
            msg_prefix="profile page should display user's display name")
        self.assertContains(response, result[0]['title'],
            msg_prefix='profile page should display article title')
        self.assertContains(response, result[0]['created'])
        self.assertContains(response, result[0]['last_modified'])
        self.assertContains(response, result[1]['title'])
        self.assertContains(response, result[1]['created'])
        self.assertContains(response, result[1]['last_modified'])
        self.assertContains(response,
                            reverse('publication:pdf', kwargs={'pid': result[0]['pid']}),
                            msg_prefix='profile should link to pdf for article')
        self.assertContains(response,
                            reverse('publication:pdf', kwargs={'pid': result[1]['pid']}),
                            msg_prefix='profile should link to pdf for article')

        # check important solr query args
        query_args, query_kwargs = self.mocksolr.query.call_args
        self.assertEqual(query_kwargs, {'owner': 'staff'})
        filter_args, filter_kwargs = self.mocksolr.query.filter.call_args
        self.assertEqual(filter_kwargs, {'content_model': Article.ARTICLE_CONTENT_MODEL})

    def test_login(self):
        login_url = reverse('accounts:login')
        # TODO: clean up wrong-password handling 
        #response = self.client.post(login_url, {'username': 'staff', 'password': 'wrong'})

        # login with valid credentials but no next
        response = self.client.post(login_url, USER_CREDENTIALS['staff'])
        expected, got = 303, response.status_code
        self.assertEqual(expected, got, 'Expected %s but got %s for successful login on %s' % \
                         (expected, got, login_url))
        self.assertEqual('http://testserver' +
                         reverse('accounts:profile', kwargs={'username': 'staff'}),
                         response['Location'],
                         'successful login with no next url should redirect to user profile')

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
