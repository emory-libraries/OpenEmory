from contextlib import contextmanager
import datetime
import hashlib
import json
import logging
import os

from django.conf import settings
from django.contrib.auth.models import AnonymousUser, User
from django.core.paginator import Paginator
from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpRequest, Http404
from django.template import context
from django.test import TestCase
from django.utils.unittest import skip

from eulfedora.server import Repository
from eulfedora.util import parse_rdf, RequestFailed
from eullocal.django.emory_ldap.backends import EmoryLDAPBackend

from mock import Mock, patch, MagicMock
from rdflib.graph import Graph as RdfGraph, Literal, RDF, URIRef
from sunburnt import sunburnt
from taggit.models import Tag

from openemory.accounts.auth import permission_required, login_required
from openemory.accounts.backends import FacultyOrLocalAdminBackend
from openemory.accounts.forms import ProfileForm
from openemory.accounts.models import researchers_by_interest, Bookmark, \
     pids_by_tag, articles_by_tag, UserProfile, EsdPerson, Degree, \
     Position, Grant, Announcement
from openemory.accounts.templatetags.tags import tags_for_user
from openemory.accounts.views import _get_profile_user
from openemory.publication.models import Article
from openemory.publication.views import ARTICLE_VIEW_FIELDS
from openemory.rdfns import DC, FRBR, FOAF
from openemory.util import solr_interface

# re-use pdf fixture from publication app
pdf_filename = os.path.join(settings.BASE_DIR, 'publication', 'fixtures', 'test.pdf')
pdf_md5sum = '331e8397807e65be4f838ccd95787880'

logger = logging.getLogger(__name__)


# credentials for test accounts in json fixture
USER_CREDENTIALS = {
    'faculty': {'username': 'faculty', 'password': 'GPnFswH9X8'},
    'student': {'username': 'student', 'password': '2Zvi4dE3fJ'},
    'super': {'username': 'super', 'password': 'awXM6jnwJj'}, 
    'admin': {'username': 'siteadmin', 'password': '8SLEYvF4Tc'},
    'jolson': {'username': 'jolson', 'password': 'qw6gsrNBWX'},
    'jmercy': {'username': 'jmercy', 'password': 'jmercy'},
}

def simple_view(request):
    "a simple view for testing custom auth decorators"
    return HttpResponse("Hello, World")

class BasePermissionTestCase(TestCase):
    '''Common setup/teardown functionality for permission_required and
    login_required tests.
    '''
    fixtures =  ['site_admin_group', 'users']
    # NOTE: site_admin_group fixture is required wherever users
    # fixture is loaded.  See DEPLOYNOTES for details.

    def setUp(self):
        self.request = HttpRequest()
        self.request.user = AnonymousUser()

        self.ajax_request = HttpRequest()
        self.ajax_request.META['HTTP_X_REQUESTED_WITH'] = 'XMLHttpRequest'
        self.ajax_request.user = AnonymousUser()
        
        self.faculty_user = User.objects.get(username='faculty')
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
        # set request to use faculty user
        self.request.user = self.faculty_user
        response = self.decorated(self.request)
        
        expected, got = 403, response.status_code
        self.assertEqual(expected, got,
                "expected status code %s but got %s for decorated view with logged-in user without perms" \
                % (expected, got))
        self.assert_("Permission Denied" in response.content,
                "response should contain content from 403.html template fixture")

        # ajax request
        self.ajax_request.user = self.faculty_user
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
        # set request to use faculty user
        self.request.user = self.faculty_user
        response = self.decorated(self.request)
        
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
                "expected status code %s but got %s for decorated view with superuser" \
                % (expected, got))
        self.assert_("Hello, World" in response.content,
                     "response should contain actual view content")


class AccountViewsTest(TestCase):
    multi_db = True
    fixtures =  ['site_admin_group', 'users', 'esdpeople']

    def setUp(self):
        self.faculty_username = 'jolson'
        self.faculty_user = User.objects.get(username=self.faculty_username)
        self.faculty_esd = EsdPerson.objects.get(netid='JOLSON')

        self.other_faculty_username = 'mmouse'
        self.other_faculty_user = User.objects.get(username=self.other_faculty_username)
        self.other_faculty_esd = EsdPerson.objects.get(netid='MMOUSE')

        # non-faculty with profile
        self.nonfaculty_username = 'jmercy'
        self.nonfaculty_user = User.objects.get(username=self.nonfaculty_username)
        self.nonfaculty_user.get_profile().nonfaculty_profile = True
        self.nonfaculty_user.get_profile().save()
        self.nonfaculty_esd = EsdPerson.objects.get(netid='JMERCY')

        self.admin_username = 'admin'
        self.student_user = User.objects.get(username='student')
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

        super(AccountViewsTest, self).tearDown()

    @patch('openemory.accounts.views.EmoryLDAPBackend')
    @patch('openemory.accounts.views.get_object_or_404')
    def test_get_profile_user(self, mockgetobj, mockldap):
        # view helper method

        # no esd person = 404
        mockgetobj.side_effect = Http404
        self.assertRaises(Http404, _get_profile_user, 'fakeuser')
        mockgetobj.assert_called_with(EsdPerson, netid='FAKEUSER')

        # existing esd person and local user/user profile with profile_page
        mockgetobj.side_effect = None
        mockgetobj.return_value = self.faculty_esd
        self.assertEqual((self.faculty_user, self.faculty_user.get_profile()),
                         _get_profile_user(self.faculty_user.username))

        # esd person & local account exist, but user should NOT have profile page
        mockgetobj.return_value = self.nonfaculty_esd
        with patch.object(self.nonfaculty_esd, 'profile') as mockprofile:
            mockprofile.return_value.has_profile_page.return_value = False
            self.assertRaises(Http404, _get_profile_user, self.nonfaculty_user.username)

        # non-faculty esd person exists but local account does not - do not init local account
        with patch.object(self.nonfaculty_esd, 'profile') as mockprofile:
            mockprofile.side_effect = UserProfile.DoesNotExist
            # esd person should not have profile page = 404
            self.assertRaises(Http404, _get_profile_user,
                              self.nonfaculty_user.username)
            # ldap should not be called when esd person should not have profile page
            self.assertEqual(0, mockldap.call_count,
                'ldap should not be called to init user when EsdPerson should not have profile')

        # faculty esd person exists without local account - init local account
        mockgetobj.return_value = self.faculty_esd
        with patch.object(self.faculty_esd, 'profile') as mockprofile:
            mockprofile.side_effect = UserProfile.DoesNotExist
            mocknewuser = Mock()
            mockldap.return_value.find_user.return_value = 'dn', mocknewuser
            user, profile = _get_profile_user(self.faculty_user.username)
            self.assertEqual(mocknewuser, user,
                'should return user initialized by ldap when User does not exist')
            self.assertEqual(1, mockldap.call_count)
            mockldap.return_value.find_user.assert_called_with(self.faculty_user.username)

            # ldap init failure
            mockldap.return_value.find_user.return_value = 'dn', None
            self.assertRaises(Http404, _get_profile_user,
                              self.nonfaculty_user.username)
            

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
    mocksolr.query.facet_by.return_value = mocksolr.query
    mocksolr.query.field_limit.return_value = mocksolr.query
    solr = solr_interface()
    mocksolr.Q.return_value = solr.Q()

    @patch('openemory.accounts.views.solr_interface', mocksolr)
    @patch('openemory.accounts.views.paginate')
    @patch('openemory.accounts.views.ArticleStatistics')
    def test_dashboard_stats(self, mockstats, mockpaginator):
        # test just the author statistics on the profile dashboard tab
        stat1 = Mock()
        stat1.num_views = 2
        stat1.num_downloads = 1
        stat2 = Mock()
        stat2.num_views = 1
        stat2.num_downloads = 1
        mockstats.objects.filter.return_value = [stat1, stat2]

        result =  [
            {'title': 'article one', 'created': 'today',
             'last_modified': 'today', 'pid': self.article.pid},
            {'title': 'article two', 'created': 'today',
             'last_modified': 'today', 'pid': 'test:pid'},
        ]
        mockpaginator.return_value = [ Paginator(result, 10).page(1), Mock() ]

        dashboard_url = reverse('accounts:dashboard',
                                kwargs={'username': self.faculty_username})

        # logged in, looking at own dashboard
        self.client.login(**USER_CREDENTIALS[self.faculty_username])
        response = self.client.get(dashboard_url)
        #print response
        
        # user stats - check for expected numbers
        self.assertContains(response, "<strong>2</strong> total items")
        self.assertContains(response, "<strong>6</strong> views on your items")
        self.assertContains(response, "<strong>4</strong> items downloaded")

    def test_dashboard_announcements(self):

        now = datetime.datetime.now()

        ann = Announcement(active=False, start=now + datetime.timedelta(days=-1),
                            end=now + datetime.timedelta(days=+1),
                            message = "You should never see this message")
        ann.save()

        ann = Announcement(active=True, start=now + datetime.timedelta(days=-1),
                            end=now + datetime.timedelta(days=+1),
                            message="Active with start and end")
        ann.save()

        ann = Announcement(active=True, end=now + datetime.timedelta(days=+1),
                            message="Active with just end")
        ann.save()

        ann = Announcement(active=True, start=now + datetime.timedelta(days=-1),
                            message="Active with just start")
        ann.save()

        ann = Announcement(active=True, message="Active with no start or end")
        ann.save()

        ann = Announcement(active=True, start=now + datetime.timedelta(days=+1),
                            message="Active but before start")
        ann.save()

        ann = Announcement(active=True, end=now + datetime.timedelta(days=-1),
                            message="Active but past end")
        ann.save()


        announcements = [a.message for a in Announcement.get_displayable()]

        self.assertEqual(len(announcements), 4)
        self.assertTrue('You should never see this message' not in announcements)
        self.assertTrue('Active with start and end' in announcements)
        self.assertTrue('Active with just end' in announcements)
        self.assertTrue('Active with just start' in announcements)
        self.assertTrue('Active but before start' not in announcements)
        self.assertTrue('Active but past end' not in announcements)

    
    @patch('openemory.accounts.views._get_profile_user')
    @patch('openemory.accounts.views.ArticleStatistics')
    def test_dashboard(self, mockstats, mockgetuser):
        # - testing dashboard/summary page of faculty profile
        dashboard_url = reverse('accounts:dashboard',
                                kwargs={'username': self.faculty_username})

        # only accessible to logged in user or site admin
        # anonymous should 401
        response = self.client.get(dashboard_url)
        expected, got = 401, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for %s as AnonymousUser' % \
                         (expected, got, dashboard_url))

        # login as faculty for following dashboard tests
        self.client.login(**USER_CREDENTIALS[self.faculty_username])
        
        mockstats.objects.filter.return_value = []
        # - use mockprofile to return an empty result for recent articles
        mockprofile = Mock()
        mockprofile.recent_articles_query.return_value = []
        mockgetuser.return_value = self.faculty_user, mockprofile
        # mock result objects
        result =  [
            {'title': 'article one', 'created': 'today', 'state': 'A',
             'last_modified': 'today', 'pid': 'a:1',
             'owner': self.faculty_username, 'dsids': ['content'],
             'parsed_author': ['nonuser:A. Non User', ':N. External User']},
            {'title': 'article two', 'created': 'yesterday', 'state': 'A',
             'last_modified': 'today','pid': 'a:2',
             'owner': self.faculty_username, 'dsids': ['contentMetadata'],
             'pmcid': '123456', 'parsed_author':
               ['nonuser:A. Non User', 'mmouse:Minnie Mouse']},
        ]
        unpub_result = [
            {'title': 'upload.pdf', 'created': 'today', 'state': 'I',
             'last_modified': 'today', 'pid': 'a:3',
             'owner': self.faculty_username}
            ]
        mockprofile.recent_articles.return_value = result
        mockprofile.unpublished_articles.return_value = unpub_result
        
        response = self.client.get(dashboard_url)
        mockprofile.recent_articles.assert_called_once()
        mockprofile.unpublished_articles.assert_called_once()

        self.assertContains(response, reverse('publication:ingest'),
            msg_prefix='user looking at their own profile page should see upload link')
#        # TODO: tag editing disabled due to design difficulties.
#        # tag editing enabled
#        self.assertTrue(response.context['editable_tags'])
#        self.assert_('tagform' in response.context)
        # unpublished articles
        self.assertContains(response, unpub_result[0]['title'])
        self.assertContains(response, reverse('publication:edit',
                                              kwargs={'pid': unpub_result[0]['pid']}),
            msg_prefix='profile should include edit link for unpublished article')
        self.assertNotContains(response, reverse('publication:edit',
                                              kwargs={'pid': result[0]['pid']}),
            msg_prefix='profile should not include edit link for published article')
        


    @patch('openemory.accounts.views._get_profile_user')
    def test_public_profile_info(self, mockgetuser):
        # anonymous user should see public profile - test user info portion
        profile_url = reverse('accounts:profile',
                kwargs={'username': self.faculty_username})
        # no articles for this test
        # - use mockprofile to return an empty result for recent articles
        mockprofile = Mock()
        mockprofile.recent_articles_query.return_value = []
        mockgetuser.return_value = self.faculty_user, mockprofile

        response = self.client.get(profile_url)
        self.assertEqual('accounts/profile.html', response.templates[0].name,
            'anonymous access to profile should use accounts/profile.html for primary template')
        
        # ESD data should be displayed (not suppressed)
        self.assertContains(response, self.faculty_esd.directory_name,
            msg_prefix="profile page should display user's directory name")
        self.assertContains(response, self.faculty_esd.title,
            msg_prefix='title from ESD should be displayed')
        self.assertContains(response, self.faculty_esd.department_name,
            msg_prefix='department from ESD should be displayed')
        self.assertContains(response, self.faculty_esd.email,
            msg_prefix='email from ESD should be displayed')
        self.assertContains(response, self.faculty_esd.phone,
            msg_prefix='phone from ESD should be displayed')
        self.assertContains(response, self.faculty_esd.fax,
            msg_prefix='fax from ESD should be displayed')
        self.assertContains(response, self.faculty_esd.ppid,
            msg_prefix='PPID from ESD should be displayed')

        # optional user-entered information
        # degrees - nothing should be shown
        self.assertNotContains(response, 'Degrees',
            msg_prefix='profile should not display degrees if none are entered')
        # bio
        self.assertNotContains(response, 'Biography',
            msg_prefix='profile should not display bio if none has been added')
        # positions
        self.assertNotContains(response, 'Positions',
            msg_prefix='profile should not display positions if none has been added')
        # grants
        self.assertNotContains(response, 'Grants',
            msg_prefix='profile should not display grants if none has been added')

        # add degrees, bio, positions, grants; then check
        faculty_profile = self.faculty_user.get_profile()
        ba_degree = Degree(name='BA', institution='Somewhere U', year=1876,
                           holder=faculty_profile)
        ba_degree.save()
        ma_degree = Degree(name='MA', institution='Elsewhere Institute',
                           holder=faculty_profile)
        ma_degree.save()
        faculty_profile.biography = 'did some **stuff**'
        faculty_profile.save()
        position = Position(name='Director of Stuff, Association of Smart People',
                            holder=faculty_profile)
        position.save()
        gouda_grant = Grant(name='Gouda research', grantor='The Gouda Group',
                            project_title='Effects of low-gravity environments on gouda aging',
                            year=1616, grantee=faculty_profile)
        gouda_grant.save()
        queso_grant = Grant(grantor='Mexican-American food research council',
                            project_title='Cheese dip and subject happiness',
                            grantee=faculty_profile)
        queso_grant.save()

        response = self.client.get(profile_url)
        self.assertContains(response, 'Degrees',
            msg_prefix='profile should display degrees if user has entered them')
        self.assertContains(response, '%s, %s, %d' % \
                            (ba_degree.name, ba_degree.institution, ba_degree.year))
        self.assertContains(response, '%s, %s' % \
                            (ma_degree.name, ma_degree.institution))
        self.assertContains(response, 'Biography',
            msg_prefix='profile should display bio when one has been added')
        self.assertContains(response, 'did some <strong>stuff</strong>',
            msg_prefix='bio text should be displayed with markdown formatting')
        self.assertContains(response, 'Director of Stuff',
            msg_prefix='position title should be displayed')
#       # TODO: Grants have been temporarily removed from the site design
#       # while problems with the editing interface are resolved. reinstate
#       # these as soon as that's available.
#        self.assertContains(response, 'Grants',
#            msg_prefix='profile should display grants when one has been added')
#        self.assertContains(response, gouda_grant.name)
#        self.assertContains(response, gouda_grant.grantor)
#        self.assertContains(response, gouda_grant.year)
#        self.assertContains(response, gouda_grant.project_title)
#        self.assertContains(response, queso_grant.grantor)
#        self.assertContains(response, queso_grant.project_title)


        # add research interests
        tags = ['myopia', 'arachnids', 'climatology']
        self.faculty_user.get_profile().research_interests.add(*tags)
        response = self.client.get(profile_url)
        self.assertContains(response, 'Research Interests',
            msg_prefix='profile page should not display "Research interests" when tags are set')
        for tag in tags:
            self.assertContains(response, tag,
                msg_prefix='profile page should display research interest tags')

        

    @patch('openemory.accounts.models.solr_interface', mocksolr)
    @patch('openemory.accounts.views.paginate')
    @patch('openemory.accounts.views._get_profile_user')
    def test_public_profile_docs(self, mockgetuser, mockpaginator):
        # test display of published documents on public profile
        profile_url = reverse('accounts:profile',
                              kwargs={'username': self.faculty_username})
        self.mocksolr.query.count.return_value = 0

        # mock result object
        result =  [
            {'title': 'article one', 'created': 'today', 'state': 'A',
             'last_modified': 'today', 'pid': 'a:1',
             'owner': self.faculty_username, 'dsids': ['content'],
             'parsed_author': ['nonuser:A. Non User', ':N. External User']},
            {'title': 'article two', 'created': 'yesterday', 'state': 'A',
             'last_modified': 'today','pid': 'a:2',
             'owner': self.faculty_username, 'dsids': ['contentMetadata'],
             'pmcid': '123456', 'parsed_author':
               ['nonuser:A. Non User', 'mmouse:Minnie Mouse']},
        ]
        # use mockprofile to supply mocks for recent & unpublished articles
        mockprofile = Mock()
        mockprofile.recent_articles.return_value = result
        mockgetuser.return_value = self.faculty_user, mockprofile
        mockpaginator.return_value = [ Paginator(result, 10).page(1), Mock() ]
        # anonymous access - unpub should not be called
        response = self.client.get(profile_url)
        mockprofile.recent_articles.assert_called_once()
        mockprofile.unpublished_articles.assert_not_called()

        self.assertContains(response, result[0]['title'],
            msg_prefix='profile page should display article title')
        self.assertContains(response, result[1]['title'])
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

        # no edit link
        edit_url = reverse('accounts:edit-profile',
                           kwargs={'username': self.faculty_username})
        self.assertNotContains(response, edit_url,
            msg_prefix='profile page edit link should not display to anonymous user')
    

    @skip('unmigrated remainder from of massive profile test')
    def test_profile(self):
        # NOTE: these tests were part of the massive profile test that
        # was testing the functionality on all tabs of the faculty dashboard
        # Some of these may still be relevant but I'm not sure where they go
        
        
                
        # logged in, looking at someone else's profile
        mockgetuser.return_value = self.other_faculty_user, self.other_faculty_user.get_profile() 
        profile_url = reverse('accounts:profile',
                kwargs={'username': self.other_faculty_username})
        response = self.client.get(profile_url)
        # tag editing not enabled
        self.assert_('editable_tags' not in response.context)
        self.assert_('tagform' not in response.context)
                
        # personal bookmarks
        bk, created = Bookmark.objects.get_or_create(user=self.faculty_user, pid=result[0]['pid'])
        super_tags = ['new', 'to read']
        bk.tags.set(*super_tags)
        response = self.client.get(profile_url)
#        # TODO: design does not currently include private tags
#        for tag in super_tags:
#            self.assertContains(response, tag,
#                 msg_prefix='user sees their private article tags in any article list view')

        # logged in as admin, looking at someone else's profile
        mockgetuser.return_value = self.faculty_user, self.faculty_user.get_profile() 

        self.client.login(**USER_CREDENTIALS[self.admin_username])
        profile_url = reverse('accounts:profile',
                kwargs={'username': self.faculty_username})
        response = self.client.get(profile_url)
        template_names = [t.name for t in response.templates]
        self.assertTrue('accounts/dashboard.html' in template_names)



    @patch('openemory.util.sunburnt.SolrInterface', mocksolr)
    @patch('openemory.accounts.views.EmoryLDAPBackend')
    def test_profile_rdf(self, mockldap):
        # mock solr result 
        result =  [
            {'title': 'article one', 'created': 'today',
             'last_modified': 'today', 'pid': self.article.pid},
        ]
        self.mocksolr.query.execute.return_value = result

        profile_url = reverse('accounts:profile',
                kwargs={'username': self.faculty_username})
        profile_uri = URIRef('http://testserver' + profile_url)
        response = self.client.get(profile_url, HTTP_ACCEPT='application/rdf+xml')
        self.assertEqual('application/rdf+xml', response['Content-Type'])

        location_url = reverse('accounts:profile-data',
                kwargs={'username': self.faculty_username})
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

        # article metadata
        for triple in self.article.as_rdf(node=article_node):
            self.assert_(triple in rdf,
                         'article rdf should be included in profile rdf graph')

        # directory data for non-suppressed user
        self.assert_((author_node, FOAF.name, Literal(self.faculty_esd.directory_name))
                     in rdf, 'author full name should be present')
        mbox_sha1sum = hashlib.sha1(self.faculty_esd.email).hexdigest()
        self.assert_((author_node, FOAF.mbox_sha1sum, Literal(mbox_sha1sum))
                     in rdf, 'author email hash should be present')
        self.assert_((author_node, FOAF.phone, URIRef('tel:' + self.faculty_esd.phone))
                     in rdf, 'author phone number should be present')

        # directory data internet-suppressed
        self.faculty_esd.internet_suppressed = True
        self.faculty_esd.save()
        response = self.client.get(profile_url, HTTP_ACCEPT='application/rdf+xml')
        rdf = parse_rdf(response.content, profile_url)
        author_node = list(rdf.objects(profile_uri, FOAF.primaryTopic))[0]

        self.assert_((author_node, FOAF.name, Literal(self.faculty_esd.directory_name))
                     in rdf, 'author full name should be present (internet suppressed)')
        mbox_sha1sum = hashlib.sha1(self.faculty_esd.email).hexdigest()
        self.assert_((author_node, FOAF.mbox_sha1sum, Literal(mbox_sha1sum))
                     not in rdf, 'author email hash should not be present (internet suppressed)')
        self.assert_((author_node, FOAF.phone, URIRef('tel:' + self.faculty_esd.phone))
                     not in rdf, 'author phone number should not be present (internet suppressed)')
        
        # directory data directory-suppressed
        self.faculty_esd.internet_suppressed = False
        self.faculty_esd.directory_suppressed = True
        self.faculty_esd.save()
        response = self.client.get(profile_url, HTTP_ACCEPT='application/rdf+xml')
        rdf = parse_rdf(response.content, profile_url)
        author_node = list(rdf.objects(profile_uri, FOAF.primaryTopic))[0]

        self.assert_((author_node, FOAF.name, Literal(self.faculty_esd.directory_name))
                     in rdf, 'author full name should be present (directory suppressed)')
        mbox_sha1sum = hashlib.sha1(self.faculty_esd.email).hexdigest()
        self.assert_((author_node, FOAF.mbox_sha1sum, Literal(mbox_sha1sum))
                     not in rdf, 'author email hash should not be present (directory suppressed)')
        self.assert_((author_node, FOAF.phone, URIRef('tel:' + self.faculty_esd.phone))
                     not in rdf, 'author phone number should not be present (directory suppressed)')

        # suppressed, local override
        faculty_profile = self.faculty_user.get_profile()
        faculty_profile.show_suppressed = True
        faculty_profile.save()
        response = self.client.get(profile_url, HTTP_ACCEPT='application/rdf+xml')
        rdf = parse_rdf(response.content, profile_url)
        author_node = list(rdf.objects(profile_uri, FOAF.primaryTopic))[0]

        self.assert_((author_node, FOAF.name, Literal(self.faculty_esd.directory_name))
                     in rdf, 'author full name should be present (directory suppressed, local override)')
        mbox_sha1sum = hashlib.sha1(self.faculty_esd.email).hexdigest()
        self.assert_((author_node, FOAF.mbox_sha1sum, Literal(mbox_sha1sum))
                     in rdf, 'author email hash should be present (directory suppressed, local override)')
        self.assert_((author_node, FOAF.phone, URIRef('tel:' + self.faculty_esd.phone))
                     in rdf, 'author phone number should be present (directory suppressed, local override)')


    # used for test_edit_profile and test_profile_photo
    profile_post_data = {
        'interests-MAX_NUM_FORMS': '',
        'interests-INITIAL_FORMS': 0,
        'interests-TOTAL_FORMS': 2,
        'interests-0-interest': 'esoteric stuff',
        'interests-0-DELETE': '',
        'interests-1-interest': '',
        'interests-1-DELETE': '',
        # degrees, with formset management fields
        '_DEGREES-MAX_NUM_FORMS': '',
        '_DEGREES-INITIAL_FORMS': 0,
        '_DEGREES-TOTAL_FORMS': 2,
        '_DEGREES-0-name': 'BA',
        '_DEGREES-0-institution': 'Somewhere Univ',
        '_DEGREES-0-year': 1876,
        '_DEGREES-1-name': 'MA',
        '_DEGREES-1-institution': 'Elsewhere Institute',
        # (degree year is optional)
        # positions, with same
        '_POSITIONS-MAX_NUM_FORMS': '',
        '_POSITIONS-INITIAL_FORMS': 0,
        '_POSITIONS-TOTAL_FORMS': 3,
        '_POSITIONS-0-name': 'Big Cheese, Association of Curd Curators',
        '_POSITIONS-1-name': 'Hole Editor, Journal of Swiss Studies',
        # grants: TODO: not currently included in templates
#        '_GRANTS-MAX_NUM_FORMS': '',
#        '_GRANTS-INITIAL_FORMS': 0,
#        '_GRANTS-TOTAL_FORMS': 3,
#        '_GRANTS-0-name': 'Advanced sharpness research',
#        '_GRANTS-0-grantor': 'Cheddar Institute',
#        '_GRANTS-0-project_title': 'The effect of subject cheesiness on cheddar sharpness assessment',
#        '_GRANTS-0-year': '1492',
#        '_GRANTS-1-grantor': u'Soci\xb4t\xb4 Brie',
#        '_GRANTS-1-project_title': 'A comprehensive analysis of yumminess',
        'biography': 'Went to school *somewhere*, studied something else **elsewhere**.',
    }

    @patch.object(EmoryLDAPBackend, 'authenticate')
    @patch('openemory.accounts.views.EmoryLDAPBackend')
    def test_edit_profile(self, mockldap, mockauth):
        mockauth.return_value = None
        edit_profile_url = reverse('accounts:edit-profile',
                                   kwargs={'username': self.faculty_username})
        
        # logged in, looking at own profile
        self.client.login(**USER_CREDENTIALS[self.faculty_username])
        response = self.client.get(edit_profile_url)
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for GET %s as %s' % \
                         (expected, got, edit_profile_url, self.faculty_username))
        self.assert_(isinstance(response.context['form'], ProfileForm),
                     'profile edit form should be set in response context')
        # non-suppressed user should not see suppression-override option
        self.assertNotContains(response, 'show_suppressed',
            msg_prefix='user who is not ESD suppressed should not see override option')

        # TODO: ESD suppression override was not included in the contracted
        # design. we need to find a place for it and put it back.
        #
        # modify ESD suppression options and check the form
        faculty_esd_data = self.faculty_user.get_profile().esd_data()
        faculty_esd_data.internet_suppressed = True
        faculty_esd_data.save()
        response = self.client.get(edit_profile_url)
        self.assertContains(response, 'show_suppressed',
            msg_prefix='user who is internet suppressed should see override option')
        faculty_esd_data.internet_suppressed = False
        faculty_esd_data.directory_suppressed = True
        faculty_esd_data.save()
        response = self.client.get(edit_profile_url)
        self.assertContains(response, 'show_suppressed',
            msg_prefix='user who is directory suppressed should see override option')


	# post invalid form data
        post_data = self.profile_post_data.copy()
        post_data['_DEGREES-0-name'] = ''
        response = self.client.post(edit_profile_url, post_data)
        self.assert_('invalid_form' in response.context)

        response = self.client.post(edit_profile_url, self.profile_post_data)
        expected, got = 303, response.status_code
        self.assertEqual(expected, got,
                         'Should get %s on successful form submission, but got %s (POST %s as %s)' % \
                         (expected, got, edit_profile_url, self.faculty_username))
        # FIXME: this should probably change
        expected = 'http://testserver' + \
                   reverse('accounts:dashboard-profile', \
                           kwargs={'username': self.faculty_username})
        self.assertEqual(expected, response['Location'])
        # degrees added
        self.assertEqual(2, self.faculty_user.get_profile().degree_set.count())
        degree = self.faculty_user.get_profile().degree_set.all()[0]
        # check that the degree was correctly created
        self.assertEqual(degree.name, 'BA')
        self.assertEqual(degree.institution, 'Somewhere Univ')
        self.assertEqual(degree.year, 1876)

        # biography added
        faculty_profile = UserProfile.objects.get(user=self.faculty_user)
        self.assertEqual(self.profile_post_data['biography'],
                         faculty_profile.biography)

        # positions added
        self.assertEqual(2, self.faculty_user.get_profile().degree_set.count())
        position = self.faculty_user.get_profile().position_set.all()[0]
        self.assertTrue(position.name.startswith('Big Cheese'))

        # grants added: TODO: grants not currently included in templates
#        self.assertEqual(2, self.faculty_user.get_profile().grant_set.count())
#        grant = self.faculty_user.get_profile().grant_set.all()[0]
#        self.assertEqual(grant.name, 'Advanced sharpness research')
#        self.assertEqual(grant.grantor, 'Cheddar Institute')
#        self.assertTrue(grant.project_title.startswith('The effect of subject cheesiness'))
#        self.assertEqual(grant.year, 1492)

        # research interests added
        self.assertEqual(1, self.faculty_user.get_profile().research_interests.count())
        interest = str(self.faculty_user.get_profile().research_interests.all()[0])
        self.assertEqual(interest, self.profile_post_data['interests-0-interest'])

        # when editing again, existing degrees should be displayed
        response = self.client.get(edit_profile_url)
        self.assertContains(response, degree.name,
            msg_prefix='existing degree name should be displayed for editing')
        self.assertContains(response, degree.institution,
            msg_prefix='existing degree institution should be displayed for editing')
        # post without required degree field
        invalid_post_data = self.profile_post_data.copy()
        invalid_post_data['_DEGREES-0-name'] = ''
        response = self.client.post(edit_profile_url,invalid_post_data)
        # FIXME: where should this go in the design?
#        self.assertContains(response, 'field is required',
#            msg_prefix='error should display when a required degree field is empty')

        # existing positions displayed
        self.assertContains(response, position.name,
            msg_prefix='existing positions should be displayed for editing')

        # existing grants displayed: TODO: grants not currently included in templates
#        self.assertContains(response, grant.name,
#            msg_prefix='existing grant name should be displayed for editing')
#        self.assertContains(response, grant.grantor,
#            msg_prefix='existing grant grantor should be displayed for editing')
#        self.assertContains(response, grant.project_title,
#            msg_prefix='existing grant project title should be displayed for editing')
#        self.assertContains(response, grant.year,
#            msg_prefix='existing grant year should be displayed for editing')

        # existing research interests displayed
        self.assertContains(response, str(interest),
            msg_prefix='existing research interests should be displayed for editing')
        
        # login as site admin
        self.client.login(**USER_CREDENTIALS['admin'])
        response = self.client.get(edit_profile_url)
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for GET %s as Site Admin' % \
                         (expected, got, edit_profile_url))

        # edit for an existing user with no profile should 404
        noprofile_edit_url = reverse('accounts:edit-profile',
                                     kwargs={'username': 'student'})
        response = self.client.get(noprofile_edit_url)
        expected, got = 404, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for %s (user with no profile)' % \
                         (expected, got, noprofile_edit_url))
        
        # edit for an non-existent user should 404
        nouser_edit_url = reverse('accounts:edit-profile',
                                     kwargs={'username': 'nosuchuser'})
        response = self.client.get(nouser_edit_url)
        expected, got = 404, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for %s (non-existent user)' % \
                         (expected, got, nouser_edit_url))

        #Check similar cases with a non-faculty user that has a profile
        edit_profile_url = reverse('accounts:edit-profile',
                                   kwargs={'username': self.nonfaculty_username})

        # logged in, looking at own profile
        self.client.login(**USER_CREDENTIALS[self.nonfaculty_username])
        response = self.client.get(edit_profile_url)
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for GET %s as %s' % \
                         (expected, got, edit_profile_url, self.faculty_username))
        self.assert_(isinstance(response.context['form'], ProfileForm),
                     'profile edit form should be set in response context')

        #Update profile
        response = self.client.post(edit_profile_url, self.profile_post_data)
        expected, got = 303, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for POST %s as %s' % \
                         (expected, got, edit_profile_url, self.nonfaculty_username))
        expected = 'http://testserver' + \
                   reverse('accounts:dashboard-profile', \
                           kwargs={'username': self.nonfaculty_username})
        self.assertEqual(expected, response['Location'])
        # degrees added
        self.assertEqual(2, self.nonfaculty_user.get_profile().degree_set.count())
        degree = self.nonfaculty_user.get_profile().degree_set.all()[0]
        # check that the degree was correctly created
        self.assertEqual(degree.name, 'BA')
        self.assertEqual(degree.institution, 'Somewhere Univ')
        self.assertEqual(degree.year, 1876)

        # biography added
        nonfaculty_profile = UserProfile.objects.get(user=self.nonfaculty_user)
        self.assertEqual(self.profile_post_data['biography'],
                         nonfaculty_profile.biography)

        # positions added
        self.assertEqual(2, self.nonfaculty_user.get_profile().degree_set.count())
        position = self.nonfaculty_user.get_profile().position_set.all()[0]
        self.assertTrue(position.name.startswith('Big Cheese'))

        # grants added: TODO: grants not currently included in template
#        self.assertEqual(2, self.nonfaculty_user.get_profile().grant_set.count())
#        grant = self.nonfaculty_user.get_profile().grant_set.all()[0]
#        self.assertEqual(grant.name, 'Advanced sharpness research')
#        self.assertEqual(grant.grantor, 'Cheddar Institute')
#        self.assertTrue(grant.project_title.startswith('The effect of subject cheesiness'))
#        self.assertEqual(grant.year, 1492)

        # research interests added
        self.assertEqual(1, self.nonfaculty_user.get_profile().research_interests.count())
        interest = str(self.nonfaculty_user.get_profile().research_interests.all()[0])
        self.assertEqual(interest, self.profile_post_data['interests-0-interest'])


    @patch.object(EmoryLDAPBackend, 'authenticate')
    def test_profile_photo(self, mockauth):
        # test display & edit profile photo
        mockauth.return_value = None
        profile_url = reverse('accounts:dashboard-profile',
                                   kwargs={'username': self.faculty_username})
        edit_profile_url = reverse('accounts:edit-profile',
                                   kwargs={'username': self.faculty_username})
        self.client.login(**USER_CREDENTIALS[self.faculty_username])
        # no photo should display
        response = self.client.get(profile_url)
        # FIXME: this is the best we have now for identifying the photo image
        self.assertNotContains(response, 'alt="photo" class="placeHolder"',
            msg_prefix='no photo should display on profile when user has not added one')

        # non-image file should error
        with open(pdf_filename) as pdf:
            post_data  = self.profile_post_data.copy()
            post_data['photo'] = pdf
            response = self.client.post(edit_profile_url, post_data)
            self.assertContains(response,
                                'either not an image or a corrupted image',
                 msg_prefix='error message is displayed when non-image is uploaded')
            
        # edit profile and add photo
        img_filename = os.path.join(settings.BASE_DIR, 'accounts',
                                    'fixtures', 'profile.gif')
        with open(img_filename) as img:
            post_data  = self.profile_post_data.copy()
            post_data['photo'] = img
            response = self.client.post(edit_profile_url, post_data)
            expected, got = 303, response.status_code
            self.assertEqual(expected, got,
                'edit with profile image; expected %s but returned %s for %s' \
                             % (expected, got, edit_profile_url))

            profile = self.faculty_user.get_profile()
            # photo should be non-empty
            self.assert_(profile.photo,
                'profile photo should be set after successful upload')
            # small photo should not be resized
            self.assertEqual(128, profile.photo.width,
                'profile photo smaller than max width should not be resized')

        # resize photo on upload
        img_filename = os.path.join(settings.BASE_DIR, 'accounts',
                                    'fixtures', 'profile_lg.gif')
        with open(img_filename) as img:
            post_data  = self.profile_post_data.copy()
            post_data['photo'] = img
            response = self.client.post(edit_profile_url, post_data)
            expected, got = 303, response.status_code
            self.assertEqual(expected, got,
                'edit with profile image; expected %s but returned %s for %s' \
                             % (expected, got, edit_profile_url))
            # get a fresh copy of the profile
            profile = UserProfile.objects.get(user=self.faculty_user)
            # large photo should be resized
            self.assertEqual(207, profile.photo.width,
                'profile photo larger than max width should be resized')


        # photo should display
        response = self.client.get(profile_url)
        self.assertContains(response, 'alt="photo" class="placeHolder"',
            msg_prefix='photo should display on profile when user has added one')


        # TODO: add styled "clear" checkbox for photo
        # user can remove photo via edit form
        post_data  = self.profile_post_data.copy()
        post_data['delete_photo'] = 'on' # remove uploaded photo
        response = self.client.post(edit_profile_url, post_data)
        expected, got = 303, response.status_code
        self.assertEqual(expected, got,
                'edit and remove profile image; expected %s but returned %s for %s' \
                             % (expected, got, edit_profile_url))
        # get a fresh copy of the profile to check
        profile = UserProfile.objects.get(user=self.faculty_user)
        # photo should be cleared
        self.assert_(not profile.photo,
                     'profile photo should be blank after cleared by user')
        
        # photo should not display
        response = self.client.get(profile_url)
        self.assertNotContains(response, 'alt="photo" class="placeHolder"',
            msg_prefix='photo should not display on profile when user has removed it')

                
    @patch.object(EmoryLDAPBackend, 'authenticate')
    @patch('openemory.publication.views.solr_interface', mocksolr)  # for home page content
    def test_login(self, mockauth):
        self.mocksolr.query.execute.return_value = MagicMock()  # needs to be iterable
        mockauth.return_value = None

        login_url = reverse('accounts:login')
        # without next - wrong password should redirect to site index
        response = self.client.post(login_url,
                {'username': self.faculty_username, 'password': 'wrong'})
        expected, got = 303, response.status_code
        self.assertEqual(expected, got, 'Expected %s but got %s for failed login on %s' % \
                         (expected, got, login_url))
        self.assertEqual('http://testserver' + reverse('site-index'),
                         response['Location'],
                         'failed login with no next url should redirect to site index')
        # with next - wrong password should redirect to next
        response = self.client.post(login_url,
                {'username': self.faculty_username, 'password': 'wrong',
                 'next': reverse('publication:ingest')})
        expected, got = 303, response.status_code
        self.assertEqual(expected, got, 'Expected %s but got %s for failed login on %s' % \
                         (expected, got, login_url))
        self.assertEqual('http://testserver' + reverse('publication:ingest'),
                         response['Location'],
                         'failed login should redirect to next url when it is specified')

        # login with valid credentials but no next
        response = self.client.post(login_url, USER_CREDENTIALS[self.faculty_username])
        expected, got = 303, response.status_code
        self.assertEqual(expected, got, 'Expected %s but got %s for successful login on %s' % \
                         (expected, got, login_url))
        self.assertEqual('http://testserver' +
                         reverse('accounts:profile',
                                 kwargs={'username': self.faculty_username}),
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
        opts.update(USER_CREDENTIALS[self.faculty_username])
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
        user = User.objects.get(username=self.faculty_username)
        tags = ['a', 'b', 'c', 'z']
        user.get_profile().research_interests.set(*tags)
        
        tag_profile_url = reverse('accounts:profile-tags',
                kwargs={'username': self.faculty_username})
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
                kwargs={'username': self.faculty_username})

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
        self.client.login(**USER_CREDENTIALS[self.faculty_username])
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
        user = User.objects.get(username=self.faculty_username)
        for tag in tags:
            self.assertTrue(user.get_profile().research_interests.filter(name=tag).exists())

    def test_tag_profile_POST(self):
        tag_profile_url = reverse('accounts:profile-tags',
                kwargs={'username': self.faculty_username})

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
        self.client.login(**USER_CREDENTIALS[self.faculty_username])
        # add initial tags to user
        initial_tags = ['one', '2']
        self.faculty_user.get_profile().research_interests.add(*initial_tags)
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
        user = User.objects.get(username=self.faculty_username)
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
        self.faculty_user.get_profile().research_interests.add('open access', 'faculty habits')
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
        self.assertContains(response, self.faculty_user.get_profile().get_full_name(),
            msg_prefix='response should display full name for users with specified interest')
        self.assertContains(response, oa_scholar.get_profile().get_full_name(),
            msg_prefix='response should display full name for users with specified interest')
        for tag in self.faculty_user.get_profile().research_interests.all():
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
        self.client.login(**USER_CREDENTIALS[self.faculty_username])
        response = self.client.get(prof_by_tag_url)
        self.assertContains(response, 'one of your research interests', 
            msg_prefix='logged in user with this interest should see indication')
        
        self.faculty_user.get_profile().research_interests.clear()
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

    def test_degree_institutions_autocomplete(self):
        # create degrees to search on
        emory = 'Emory University'
        gatech = 'Georgia Tech'
        uga = 'University of Georgia'
        faculty_profile = self.faculty_user.get_profile()
        ba_degree, created = Degree.objects.get_or_create(name='BA',
                               institution=emory, holder=faculty_profile)
        ma_degree, created = Degree.objects.get_or_create(name='MA',
                               institution=emory, holder=faculty_profile)
        ms_degree, created = Degree.objects.get_or_create(name='MS',
                               institution=gatech, holder=faculty_profile)
        ba_degree, created = Degree.objects.get_or_create(name='BA',
                               institution=uga, holder=faculty_profile)

        degree_inst_autocomplete_url = reverse('accounts:degree-autocomplete',
                                               kwargs={'mode': 'institution'})
        response = self.client.get(degree_inst_autocomplete_url,
                                   {'term': 'emory'})
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for %s' % \
                         (expected, got, degree_inst_autocomplete_url))
        # inspect return response
        self.assertEqual('application/json', response['Content-Type'],
             'should return json on success')
        data = json.loads(response.content)
        self.assert_(data, "Response content successfully read as JSON")
        self.assertEqual(1, len(data),
            'response includes only one matching instutition')
        self.assertEqual(emory, data[0]['value'],
            'response includes expected instutition name')
        self.assertEqual(emory, data[0]['label'],
            'display label has  correct term count')
        # partial match
        response = self.client.get(degree_inst_autocomplete_url,
                                   {'term': 'univ'})
        data = json.loads(response.content)
        self.assertEqual(emory, data[0]['label'],
            'match with most matches is listed first (without count)')
        self.assertEqual(uga, data[1]['label'],
            'match with second most matches is listed second (without count)')

        # test degree name autocompletion
        degree_name_autocomplete_url = reverse('accounts:degree-autocomplete',
                                               kwargs={'mode': 'name'})
        response = self.client.get(degree_name_autocomplete_url,
                                   {'term': 'm'})
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for %s' % \
                         (expected, got, degree_name_autocomplete_url))
        # inspect return response
        self.assertEqual('application/json', response['Content-Type'],
             'should return json on success')
        data = json.loads(response.content)
        self.assert_(data, "Response content successfully read as JSON")
        self.assertEqual(2, len(data),
            'response includes two matching degree names')
        degree_names = [d['label'] for d in data]
        self.assert_('MA' in degree_names)
        self.assert_('MS' in degree_names)

    def test_position_autocomplete(self):
        # create positions to search on
        emory = ''
        gatech = 'Vice Dude Ga Tech'
        uga = 'Grunt UGA'
        faculty_profile = self.faculty_user.get_profile()
        faculty_profile.position_set.add(Position(name='Head Dude Emory'))
        faculty_profile.position_set.add(Position(name='Vice Dude Ga Tech'))
        #duplicate would not normally happen on the same account but used to test facet
        faculty_profile.position_set.add(Position(name='Vice Dude Ga Tech'))
        faculty_profile.position_set.add(Position(name='Grunt UGA'))
        faculty_profile.save()


        position_autocomplete_url = reverse('accounts:position-autocomplete')
        response = self.client.get(position_autocomplete_url, {'term': 'dude'})
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for %s' % \
                         (expected, got, position_autocomplete_url))
        self.assertEqual('application/json', response['Content-Type'],
             'should return json on success')

        data = json.loads(response.content)
        self.assertTrue(isinstance(data, list))
        self.assertTrue({'value':'Head Dude Emory', 'label':'Head Dude Emory (1)'} in data, 'Value should be in json return')
        self.assertTrue({'value':'Vice Dude Ga Tech', 'label':'Vice Dude Ga Tech (2)'} in data,'Value should be in json return')





    @patch('openemory.accounts.views.solr_interface', mocksolr)
    def test_faculty_autocomplete(self):
        mock_result = [
            {'ad_name': 'Kohler, James J',
             'username': 'jjkohle',
             'first_name': 'James J',
             'last_name': 'Kohler',
             'department_name': 'SOM: Peds: VA Lab Biochem'
             }
        ]
        _old_result = self.mocksolr.query.execute.return_value 
        self.mocksolr.query.execute.return_value = mock_result

        faculty_autocomplete_url = reverse('accounts:faculty-autocomplete')
        # anonymous access restricted (faculty data)
        response = self.client.get(faculty_autocomplete_url,
                                   {'term': 'mouse'})
        expected, got = 401, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for %s as Anonymous User' % \
                         (expected, got, faculty_autocomplete_url))

        # login as faculty user for remaining tests
        self.client.login(**USER_CREDENTIALS[self.faculty_username])
        response = self.client.get(faculty_autocomplete_url,
                                   {'term': 'kohl'})
        self.assertEqual('application/json', response['Content-Type'],
             'should return json on success')
        data = json.loads(response.content)
        self.assert_(data, "Response content successfully read as JSON")
        # fields returned - needed for form-side javascript
        for field in ['username', 'first_name', 'last_name', 'description', 'label']:
            self.assert_(field in data[0],
                         'field %s should be included in the json return')

        # inspect solr query args
        args, kwargs = self.mocksolr.query.filter.call_args
        self.assertEqual(EsdPerson.record_type, kwargs['record_type'],
                         'solr query should filter on record type for EsdPerson')
        kwargs_list = [kw for a, kw in self.mocksolr.Q.call_args_list]
        self.assert_({'ad_name': 'kohl'} in kwargs_list,
                     'Solr query should look for ad_name exact match')
        self.assert_({'ad_name': 'kohl*'} in kwargs_list,
                     'Solr query should look for ad_name wildcard match')
        sort_by = [args[0] for args, kwargs in self.mocksolr.query.sort_by.call_args_list]
        self.assertEqual('-score', sort_by[0],
                         'solr query should be sorted first by relevance')
        self.assertEqual('ad_name_sort', sort_by[1],
                         'solr query should be sorted second by lastname, first')

        # multi-term match with comma
        response = self.client.get(faculty_autocomplete_url,
                                   {'term': 'nodine, la'})
        kwargs_list = [kw for a, kw in self.mocksolr.Q.call_args_list]
        self.assert_({'ad_name': 'nodine'} in kwargs_list,
                    'query should include first term exact match')
        self.assert_({'ad_name': 'nodine*'} in kwargs_list,
                    'query should include first term wildcard match')
        self.assert_({'ad_name': 'la'} in kwargs_list,
                    'query should include second term exact match')
        self.assert_({'ad_name': 'la*'} in kwargs_list,
                    'query should include second term wildcard match')

        # FIXME: test_profile fails without this restored (?!?)
        self.mocksolr.query.execute.return_value = _old_result


    def test_tag_object_GET(self):
        # create a bookmark to get
        bk, created = Bookmark.objects.get_or_create(user=self.faculty_user, pid='pid:test1')
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
        self.client.login(**USER_CREDENTIALS[self.faculty_username])

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
        self.client.login(**USER_CREDENTIALS[self.faculty_username])
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
        self.assertTrue(Bookmark.objects.filter(user=self.faculty_user, pid=testpid).exists())
        bk = Bookmark.objects.get(user=self.faculty_user, pid=testpid)
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
        bk = Bookmark.objects.get(user=self.faculty_user, pid=testpid)
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
        bk1, new = Bookmark.objects.get_or_create(user=self.faculty_user, pid='test:1')
        bk1.tags.set('foo', 'bar', 'baz')
        bk2, new = Bookmark.objects.get_or_create(user=self.faculty_user, pid='test:2')
        bk2.tags.set('foo', 'bar')
        bk3, new = Bookmark.objects.get_or_create(user=self.faculty_user, pid='test:3')
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

        self.client.login(**USER_CREDENTIALS[self.faculty_username])
        response = self.client.get(tag_autocomplete_url, {'s': 'foo'})
        expected, got = 200, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for %s' % \
                         (expected, got, tag_autocomplete_url))
        data = json.loads(response.content)
        # check return response
        self.assertEqual('foo', data[0]['value'],
            'response includes matching tag')
        # faculty user has 3 foo tags
        self.assertEqual('foo (3)', data[0]['label'],
            'display label includes count for current user')
        
        # multiple tags - autocomplete the last one only
        response = self.client.get(tag_autocomplete_url, {'term': 'bar, baz, fo'})
        data = json.loads(response.content)
        # check return response
        self.assertEqual(1, len(data),
            'response should only include one matching tag')
        self.assertEqual('foo (3)', data[0]['label'],
            'response includes matching tag for last term')
        self.assertEqual('bar, baz, foo, ', data[0]['value'],
            'response value includes entire term list with completed tag')

        # login as different user - should get count for their own bookmarks only
        self.client.login(**USER_CREDENTIALS['super'])
        response = self.client.get(tag_autocomplete_url, {'s': 'foo'})
        data = json.loads(response.content)
        # super user has 2 foo tags
        self.assertEqual('foo (2)', data[0]['label'],
            'display label includes correct term count')

    @skip('tags do not appear in contracted design')
    def test_tags_in_sidebar(self):
        # create some bookmarks with tags to search on
        bk1, new = Bookmark.objects.get_or_create(user=self.faculty_user, pid='test:1')
        bk1.tags.set('full text', 'to read')
        bk2, new = Bookmark.objects.get_or_create(user=self.faculty_user, pid='test:2')
        bk2.tags.set('to read')

        profile = self.faculty_user.get_profile()
        profile.research_interests.set('ponies')
        profile.save()

        # can really test any page for this...
        profile_url = reverse('accounts:profile',
                kwargs={'username': self.faculty_username})

        # not logged in - no tags in sidebar
        response = self.client.get(profile_url)
        self.assertFalse(response.context['tags'],
            'no tags should be set in response context for unauthenticated user')
        self.assertNotContains(response, '<h2>Tags</h2>',
             msg_prefix='tags should not be displayed in sidebar for unauthenticated user')

        # log in to see tags
        self.client.login(**USER_CREDENTIALS[self.faculty_username])
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
        bk1, new = Bookmark.objects.get_or_create(user=self.faculty_user, pid='test:1')
        bk1.tags.set('full text', 'to read')
        bk2, new = Bookmark.objects.get_or_create(user=self.faculty_user, pid='test:2')
        bk2.tags.set('to read')

        tagged_item_url = reverse('accounts:tag', kwargs={'tag': 'to-read'})

        # not logged in - no access
        response = self.client.get(tagged_item_url)
        expected, got = 401, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for %s (not logged in)' % \
                         (expected, got, tagged_item_url))
        
        # log in to see tagged items
        self.client.login(**USER_CREDENTIALS[self.faculty_username])
        mockart_by_tag.return_value = [
            {'title': 'test article 1', 'pid': 'test:1'},
            {'title': 'test article 2', 'pid': 'test:2'}
        ]
        response = self.client.get(tagged_item_url)
        # check mock solr response, response display
        mockart_by_tag.assert_called_with(self.faculty_user, bk2.tags.all()[0])
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

    @patch('openemory.accounts.views.solr_interface', mocksolr)
    def test_list_departments(self):
        mockfacets = {
            'division_dept_id': [
                ('School Of Law|UBX|School of Law|881420', 1),
                ('School Of Medicine|UCX|Neurosurgery|734000', 2),
                ('School Of Medicine|UCX|Physiology|736526', 1),
                ('University Libraries|U9X|University Libraries|921060', 2)
                ]}
        self.mocksolr.query.execute.return_value.facet_counts.facet_fields  = mockfacets
        
        list_dept_url = reverse('accounts:list-departments')
        response = self.client.get(list_dept_url)
        # check listings based on esdpeople fixture
        self.assertContains(response, 'School Of Law', count=1,
            msg_prefix='division name with same department name should only appear once')
        self.assertContains(response, 'School Of Medicine', count=1,
            msg_prefix='division name should only appear once')
        self.assertNotContains(response, 'SOM:',
            msg_prefix='division prefix on department name should not be listed')
        self.assertContains(response, 'Neurosurgery',
            msg_prefix='department name should be listed')
        self.assertContains(response, 'Physiology',
            msg_prefix='department name should be listed')
        # link to department pages
        self.assertContains(response, reverse('accounts:department',
                                              kwargs={'id': '736526'}))
        self.assertContains(response, reverse('accounts:department',
                                              kwargs={'id': '921060'}))

        # inspect solr query args
        self.mocksolr.query.assert_called_with(record_type=EsdPerson.record_type)
        self.mocksolr.query.facet_by.assert_called_with('division_dept_id',
                                                        limit=-1,
                                                        sort='index') 
        self.mocksolr.query.paginate.assert_called_with(rows=0) 

    @patch('openemory.accounts.views.solr_interface', mocksolr)
    def test_view_department(self):
        faculty_esd = self.faculty_user.get_profile().esd_data()

        mockresult = [
            {'username': self.faculty_username,
             'division_name': faculty_esd.division_name,
             'department_name': faculty_esd.department_name,
             'first_name': faculty_esd.first_name,
             'last_name': faculty_esd.last_name,
             'directory_name': faculty_esd.directory_name }
            ]
        self.mocksolr.query.execute.return_value = mockresult
#        people = solr.query(department_id=id).filter(record_type=EsdPerson.record_type) \
 #                .execute()

        dept_url = reverse('accounts:department',
                           kwargs={'id': faculty_esd.department_id})
        response = self.client.get(dept_url)
        self.assertContains(response, faculty_esd.division_name,
            msg_prefix='department page should include division name')
        self.assertContains(response, faculty_esd.department_shortname,
            msg_prefix='department page should include department name (short version)')
        self.assertNotContains(response, faculty_esd.department_name,
            msg_prefix='department page should not include department name with division prefix')
        self.assertContains(response, faculty_esd.directory_name,
            msg_prefix='department page should list faculty member full name')
        self.assertContains(response, reverse('accounts:profile',
                                              kwargs={'username': self.faculty_user.username}),
            msg_prefix='department page should link to faculty member profile')

        # division / department with same name (University Libraries)
        EUL = 'University Libraries'
        mockresult[0].update({'division_name': EUL, 'department_name': EUL})

        ul_dept_id = '921060'
        dept_url = reverse('accounts:department', kwargs={'id': ul_dept_id})
        response = self.client.get(dept_url)
        self.assertContains(response, EUL, count=2,
            msg_prefix='when department name matches division name, it should not be repeated')

        # non-existent department id should 404
        self.mocksolr.query.execute.return_value = []
        non_dept_url = reverse('accounts:department', kwargs={'id': '00000'})
        response = self.client.get(non_dept_url)
        expected, got = 404, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but got %s for %s (invalid department id)' % \
                         (expected, got, non_dept_url))
        
    def test_grant_autocomplete(self):
        # FIXME: use fixtures for these
        g = Grant(grantee=self.faculty_user.get_profile(), grantor="Hard Cheese Research Council")
        g.save()
        g = Grant(grantee=self.faculty_user.get_profile(), grantor="Soft Cheese Research Council")
        g.save()
        g = Grant(grantee=self.faculty_user.get_profile(), grantor="American Soft Tissue Association")
        g.save()

        url = reverse('accounts:grant-autocomplete')

        response = self.client.get(url, {'term': 'cheese'})
        self.assertEqual(200, response.status_code, 'matching autocomplete request failed')
        data = json.loads(response.content)
        self.assertEqual(2, len(data))
        self.assertTrue('Soft Cheese Research Council' in data)

        response = self.client.get(url, {'term': 'burger'})
        self.assertEqual(200, response.status_code, 'non-matching autocomplete request failed')
        data = json.loads(response.content)
        self.assertEqual(0, len(data))

    @patch('openemory.accounts.context_processors.solr_interface', mocksolr)
    @patch('openemory.publication.views.solr_interface', mocksolr)  # for home page content
    def test_statistics_processor(self):
        self.mocksolr.query.execute.return_value = MagicMock()  # needs to be iterable
        self.mocksolr.query.execute.return_value.result.numFound = 42

        with self._use_statistics_context():
            index_url = reverse('site-index')
            response = self.client.get(index_url)
            self.assertTrue('ACCOUNT_STATISTICS' in response.context)
            self.assertEqual(42, response.context['ACCOUNT_STATISTICS']['total_users'])
        
    @contextmanager
    def _use_statistics_context(self):
        '''Temporarily reinstate the account statistics context processor.
        This is normally included in settings.py, but testsettings.py takes
        it out: The context processor queries solr, and we don't want to
        have to mock out solr for every single view test. This context
        manager selectively re-enables it so that we can test the context
        processor itself.
        '''
        settings.TEMPLATE_CONTEXT_PROCESSORS.append('openemory.accounts.context_processors.statistics')
        context._standard_context_processors = None
        try:
            yield
        finally:
            settings.TEMPLATE_CONTEXT_PROCESSORS.remove('openemory.accounts.context_processors.statistics')
            context._standard_context_processors = None

        
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
    multi_db = True
    fixtures = ['site_admin_group', 'users', 'esdpeople']

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
    mocksolr.query.facet_by.return_value = mocksolr.query
    mocksolr.query.field_limit.return_value = mocksolr.query

    def setUp(self):
        self.user = User.objects.get(username='student')
        self.mmouse = User.objects.get(username='mmouse')
        self.smcduck = User.objects.get(username='smcduck')
        self.jmercy = User.objects.get(username='jmercy')
        
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

    def test_esd_data(self):
        self.assertEqual(self.mmouse.get_profile().esd_data().ppid, 'P9418306')
        with self.assertRaises(EsdPerson.DoesNotExist):
            self.user.get_profile().esd_data()

    def test_has_profile_page(self):
        self.assertTrue(self.mmouse.get_profile().has_profile_page()) # esd data, is faculty
        self.assertFalse(self.smcduck.get_profile().has_profile_page()) # esd data, not faculty
        self.assertFalse(self.user.get_profile().has_profile_page()) # no esd data
        self.assertFalse(self.user.get_profile().nonfaculty_profile) # should be false by default

        # set nonfaculty_profile true so jmercy can see profile
        # even though he is not faculty
        self.jmercy.get_profile().nonfaculty_profile = True
        self.jmercy.get_profile().save()
        self.assertTrue(self.jmercy.get_profile().has_profile_page()) # has nonfaculty_profile flag set

    def test_suppress_esd_data(self):
        # set both suppressed options to false - should be not suppressed
        mmouse_profile = self.mmouse.get_profile()
        esd_data = mmouse_profile.esd_data()
        esd_data.internet_suppressed = False
        esd_data.directory_suppressed = False
        esd_data.save()
        self.assertEqual(False, mmouse_profile.suppress_esd_data,
            'profile without ESD suppression should not be suppressed')
        # internet suppressed or directory suppressed
        esd_data = mmouse_profile.esd_data()
        esd_data.internet_suppressed = True
        esd_data.save()
        self.assertEqual(True, mmouse_profile.suppress_esd_data,
            'internet suppressed profile should be suppressed')
        esd_data.internet_suppressed = False
        esd_data.directory_suppressed = True
        self.assertEqual(True, mmouse_profile.suppress_esd_data,
            'directory suppressed profile should be suppressed')
        mmouse_profile.show_suppressed = True
        self.assertEqual(False, mmouse_profile.suppress_esd_data,
            'directory suppressed profile with local override should NOT be suppressed')


class TagsTemplateFilterTest(TestCase):
    fixtures = ['site_admin_group', 'users']

    def setUp(self):
        self.faculty_user = User.objects.get(username='faculty')
        testpid = 'foo:1'
        self.solr_return = {'pid': testpid}
        repo = Repository()
        self.obj = repo.get_object(pid=testpid)

    def test_anonymous(self):
        # anonymous - no error, no tags
        self.assertEqual([], tags_for_user(self.solr_return, AnonymousUser()))

    def test_no_bookmark(self):
        # should not error
        self.assertEqual([], tags_for_user(self.solr_return, self.faculty_user))

    def test_bookmark(self):
        # create a bookmark to query
        bk, created = Bookmark.objects.get_or_create(user=self.faculty_user,
                                                     pid=self.obj.pid)
        mytags = ['ay', 'bee', 'cee']
        bk.tags.set(*mytags)

        # query for tags by solr return
        tags = tags_for_user(self.solr_return, self.faculty_user)
        self.assertEqual(len(mytags), len(tags))
        self.assert_(isinstance(tags[0], Tag))
        tag_names = [t.name for t in tags]
        for tag in mytags:
            self.assert_(tag in tag_names)

        # query for tags by object - should be same
        obj_tags = tags_for_user(self.obj, self.faculty_user)
        self.assert_(all(t in obj_tags for t in tags))


    def test_no_pid(self):
        # passing in an object without a pid shouldn't error either
        self.assertEqual([], tags_for_user({}, self.faculty_user))
       

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


class FacultyOrLocalAdminBackendTest(TestCase):
    multi_db = True
    fixtures =  ['site_admin_group', 'users', 'esdpeople']

    def setUp(self):
        self.backend = FacultyOrLocalAdminBackend()
        self.faculty_username = 'jolson'
        self.non_faculty_username = 'smcduck'

    @patch.object(EmoryLDAPBackend, 'authenticate')
    def test_authenticate_local(self, mockauth):
        mockauth.return_value = True
        # not in local db
        self.assertEqual(None, self.backend.authenticate('nobody', 'pwd'),
                         'authenticate should not be called for non-db user')
        self.assertEqual(0, mockauth.call_count)
        # student in local db
        self.assertEqual(None, self.backend.authenticate(USER_CREDENTIALS['student']['username'],
                                                         USER_CREDENTIALS['student']['password']),
                         'authenticate should not be called for student in local db')
        self.assertEqual(0, mockauth.call_count)

        # super-user in local db
        self.assertEqual(True, self.backend.authenticate(USER_CREDENTIALS['super']['username'],
                                                         USER_CREDENTIALS['super']['password']),
                         'authenticate should be called for superuser in local db')
        self.assertEqual(1, mockauth.call_count)
        
        # site-admin in local db
        self.assertEqual(True, self.backend.authenticate(USER_CREDENTIALS['admin']['username'],
                                                         USER_CREDENTIALS['admin']['password']),
                         'authenticate should be called for site admin in local db')
        self.assertEqual(2, mockauth.call_count)
                
    @patch.object(EmoryLDAPBackend, 'authenticate')        
    def test_authenticate_esd_faculty(self, mockauth):
        mockauth.return_value = True

        # non-faculty
        self.assertEqual(None, self.backend.authenticate(self.non_faculty_username, 'pwd'),
                         'authenticate should not be called for esd non-faculty person')
        self.assertEqual(0, mockauth.call_count)
        
        # non-faculty with nonfaculty_profile
        non_faculty_user = User.objects.get(username=self.non_faculty_username)
        non_faculty_user.get_profile().nonfaculty_profile=True
        non_faculty_user.get_profile().save()
        self.assertEqual(True, self.backend.authenticate(self.non_faculty_username, 'pwd'),
                         'authenticate should be called for esd non-faculty person if nonfaculty_profile is set')
        self.assertEqual(1, mockauth.call_count)

        # faculty
        self.assertEqual(True, self.backend.authenticate(self.faculty_username, 'pwd'),
                         'authenticate should be called for esd faculty person')
        self.assertEqual(2, mockauth.call_count)


class EsdPersonTest(TestCase):
    multi_db = True
    fixtures =  ['site_admin_group', 'users', 'esdpeople']

    def setUp(self):
        self.mmouse = User.objects.get(username='mmouse')
        
    def test_index_data(self):
        # set both suppressed options to false
        mmouse_profile = self.mmouse.get_profile()
        esd_data = mmouse_profile.esd_data()
        esd_data.internet_suppressed = False
        esd_data.directory_suppressed = False

        self.assertEqual(esd_data, esd_data.index_data(),
            'when not internet or directory suppressed, index_data should return Esdperson')

        # internet suppressed or directory suppressed
        esd_data = mmouse_profile.esd_data()
        esd_data.internet_suppressed = True
        idx = esd_data.index_data()
        self.assert_(isinstance(idx, dict),
                     'index_data should return dictionary for suppressed users')
        # minimal metadata - currently only 7 fields
        self.assertEqual(7, len(idx.keys()))
        # check that the right fields are set
        # - based ic/type fields
        self.assert_('id' in idx)
        self.assert_('ppid' in idx)
        self.assert_('record_type' in idx)
        # - minimal name info for co-author suggestion
        self.assert_('username' in idx)
        self.assert_('ad_name' in idx)
        self.assert_('first_name' in idx)
        self.assert_('last_name' in idx)

        esd_data.internet_suppressed = False
        esd_data.directory_suppressed = True
        self.assert_(isinstance(esd_data.index_data(), dict))

        mmouse_profile.show_suppressed = True
        mmouse_profile.save()
        self.assert_(not isinstance(esd_data.index_data(), dict))

    def test_first_name(self):
        self.assertEqual('Minnie', self.mmouse.get_profile().esd_data().first_name,
                         'first_name should use firstmid_name when available')
        lnodine_esd = EsdPerson.objects.get(netid='LNODINE')
        self.assertEqual('Lawrence K.', lnodine_esd.first_name,
                         'first_name should be inferred from full name when firstmid_name is empty')
