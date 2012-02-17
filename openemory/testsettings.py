from settings import *

# remove PIDMAN settings - no need to generate PIDs when testing
PIDMAN_HOST = None
PIDMAN_USER = None
PIDMAN_PASSWORD = None
PIDMAN_DOMAIN = None

# Disable statistics during testing. The statistics processors query solr to
# get current article and faculty statistics. This is great for the live
# site, but we don't want to have to mock out solr for every view test.
TEMPLATE_CONTEXT_PROCESSORS.remove('openemory.accounts.context_processors.statistics')
TEMPLATE_CONTEXT_PROCESSORS.remove('openemory.publication.context_processors.statistics')
