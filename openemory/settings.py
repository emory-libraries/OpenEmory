# file openemory/settings.py
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

# Django settings for openemory project.

import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LISTSERV = (('OpenEmory Administrator', 'openemory@listserv.cc.emory.edu'),)
# If you set this to False, Django will make some optimizations so as not
# to load the internationalization machinery.
USE_I18N = True

# If you set this to False, Django will not format dates, numbers and
# calendars according to the current locale
USE_L10N = True

# URL that handles the media served from MEDIA_ROOT. Make sure to use a
# trailing slash.
# Examples: "http://media.lawrence.com/media/", "http://example.com/media/"
MEDIA_URL = '/media/'

# Absolute path to the directory static files should be collected to.
# Don't put anything in this directory yourself; store your static files
# in apps' "static/" subdirectories and in STATICFILES_DIRS.
# Example: "/home/media/media.lawrence.com/static/"
STATIC_ROOT = os.path.join(BASE_DIR, '..', 'static')

# URL prefix for static files.
# Example: "http://media.lawrence.com/static/"
STATIC_URL = '/static/'

# URL prefix for admin static files -- CSS, JavaScript and images.
# Make sure to use a trailing slash.
# Examples: "http://foo.com/static/admin/", "/static/admin/".
ADMIN_MEDIA_PREFIX = '/static/admin/'
LISTSERV = (('OpenEmory Administrator', 'openemory@listserv.cc.emory.edu'),)
# Additional locations of static files
STATICFILES_DIRS = (
    # Put strings here, like "/home/html/static" or "C:/www/django/static".
    # Always use forward slashes, even on Windows.
    # Don't forget to use absolute paths, not relative paths.
    os.path.join(BASE_DIR, '..', 'sitemedia'),
)

# List of finder classes that know how to find static files in
# various locations.
STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
#    'django.contrib.staticfiles.finders.DefaultStorageFinder',
)

# List of callables that know how to import templates from various sources.
TEMPLATE_LOADERS = (
    'django.template.loaders.filesystem.Loader',
    'django.template.loaders.app_directories.Loader',
#     'django.template.loaders.eggs.Loader',
)

TEMPLATE_CONTEXT_PROCESSORS = [
    # defaults:
    "django.contrib.auth.context_processors.auth",
    "django.core.context_processors.debug",
    "django.core.context_processors.i18n",
    "django.core.context_processors.media",
    "django.core.context_processors.static",
    "django.core.context_processors.tz",
    "django.contrib.messages.context_processors.messages",

    # application-specific:
    "openemory.version_context",
    "openemory.context_processors.debug",
    "openemory.context_processors.sitepages",
    "openemory.context_processors.site_analytics",
    "openemory.mx.context_processors.downtime_context",
    "openemory.accounts.context_processors.authentication_context",
    "openemory.accounts.context_processors.user_tags",
    "openemory.accounts.context_processors.statistics",
    "openemory.publication.context_processors.search_form",
    "openemory.publication.context_processors.statistics",
]

MIDDLEWARE_CLASSES = (
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'openemory.mx.middleware.DownpageMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'tracking.middleware.VisitorTrackingMiddleware',
    # flatpages middleware should always be last (fallback for 404)
    'django.contrib.flatpages.middleware.FlatpageFallbackMiddleware',
)

ROOT_URLCONF = 'openemory.urls'

TEMPLATE_DIRS = (
    # Put strings here, like "/home/html/django_templates" or "C:/www/django/templates".
    # Always use forward slashes, even on Windows.
    # Don't forget to use absolute paths, not relative paths.
    os.path.join(BASE_DIR, '..', 'templates'),
)

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.admin',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.messages',
    'django.contrib.sitemaps',
    'django.contrib.staticfiles',
    'django.contrib.markup',
    'django.contrib.humanize',
    'django.contrib.flatpages',
    'localflavor',
    'eulfedora',
    'eulcommon.searchutil',
    'eullocal.django.emory_ldap',
    'south',
    'taggit',
    'tracking',
    'openemory.mx',
    'downtime',
    'openemory.accounts',
    'openemory.common',
    'openemory.publication',
    'openemory.harvest',
    'widget_tweaks',
]

AUTH_PROFILE_MODULE = 'accounts.UserProfile'
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'openemory.accounts.backends.FacultyOrLocalAdminBackend',
]

PID_ALIASES = {
    'oe-collection' : 'info:fedora/emory-control:OpenEmory-collection'
}

# name authority number for pids managed by the configured pidmanager
PID_NAAN = 25593

FILE_UPLOAD_HANDLERS = (
    # removing default MemoryFileUploadHandler so all uploaded files can be treated the same
    'django.core.files.uploadhandler.TemporaryFileUploadHandler',
)

# session configuration
SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'
SESSION_COOKIE_AGE = 604800   # 1 week (Django default is 2 weeks)
SESSION_COOKIE_SECURE = True  # mark cookie as secure, only transfer via HTTPS
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# exempted paths for downtime
# add default /admin so it can be changed if accidentally set
DOWNTIME_EXEMPT_PATHS = (
   '/db-admin',
   '/admin',
   '/indexdata',
)

# list of IPs that can access the site despite downtime
DOWNTIME_ALLOWED_IPS = []

try:
    from localsettings import *
except ImportError:
    import sys
    print >>sys.stderr, '''Settings not defined. Please configure a version
        of localsettings.py for this site. See localsettings.py.dist for
        setup details.'''
    del sys

# route ESD objects to ESD database
DATABASE_ROUTERS = ['openemory.accounts.db.EsdRouter']

# django_nose configurations

django_nose = None
try:
    # NOTE: errors if DATABASES is not configured (in some cases),
    # so this must be done after importing localsettings
    import django_nose
except ImportError:
    pass

# - only if django_nose is installed, so it is only required for development
if django_nose is not None:
    INSTALLED_APPS.append('django_nose')
    TEST_RUNNER = 'django_nose.NoseTestSuiteRunner'
    NOSE_PLUGINS = [
        'eulfedora.testutil.EulfedoraSetUp',
        'openemory.testutil.UnManagedModels',
        # ...
    ]
    NOSE_ARGS = ['--with-eulfedorasetup']
    TEST_OUTPUT_DIR = 'test-results'



# disable south tests and migrations when running tests
# - without these settings, test fail on loading initial fixtured data
SKIP_SOUTH_TESTS = True
SOUTH_TESTS_MIGRATE = False

SOUTH_DATABASE_ADAPTERS = {
    'default': 'south.db.mysql'
}

if 'DJANGO_TEST_MODE' in os.environ:
    # TODO: convert this into a nose plugin
    print "MODIFYING CONTEXT PROCESSORS FOR TEST"
    TEMPLATE_CONTEXT_PROCESSORS.remove('openemory.accounts.context_processors.statistics')
    TEMPLATE_CONTEXT_PROCESSORS.remove('openemory.publication.context_processors.statistics')
    # remove real pidman settings so that tests don't create test pids
    PIDMAN_HOST = None
