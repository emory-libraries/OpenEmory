from mock import Mock
from django.conf import settings
from django.http import HttpResponse, HttpRequest
from django.test import TestCase
from django.contrib.auth.models import User, AnonymousUser

from openemory.accounts.auth import permission_required, login_required

def simple_view(request):
    "a simple view for testing custom auth decorators"
    return HttpResponse("Hello, World")

class BasePermissionTestCase(TestCase):
    '''Common setup/teardown functionality for permission_required and
    login_required tests.
    '''

    def setUp(self):
        self.request = HttpRequest()
        self.request.user = AnonymousUser()

        # mock users to simulate a staff user and a superuser
        staff_user = Mock(spec=User, name='MockStaffUser')
        staff_user.username = 'staff'
        # staff user is authenticated, but doesn't have permission to do anything
        staff_user.is_authenticated.return_value = True
        staff_user.has_perm.return_value = False
        # superuser allowed to do anything
        super_user = Mock(spec=User, name='MockSuperUser')
        super_user.username = 'super'
        super_user.is_authenticated.return_value = True
        super_user.has_perm.return_value = True

        self.staff_user = staff_user
        self.super_user = super_user

        # certain context processors fail with the mock users /
        # limited request used here; disable for these permission decorator tests
        self._context_proc = list(settings.TEMPLATE_CONTEXT_PROCESSORS)
        settings.TEMPLATE_CONTEXT_PROCESSORS = ()
        
    def tearDown(self):
        # restore configured context processors
        settings.TEMPLATE_CONTEXT_PROCESSORS = self._context_proc


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
