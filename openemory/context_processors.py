# file openemory/context_processors.py
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

from django.conf import settings
from django.contrib.flatpages.models import FlatPage
from django.template import context_processors

def debug(request):
    '''Return context variables that may be helpful for debugging.
    Extends :meth:`django.core.context_processors.debug` to include
    output from a secondary (esd) database.

    Runs the :meth:`django.core.context_processors.debug`; if the
    returned context indicates that debugging should be enabled and
    the ``esd`` database is configured, adds any queries made against
    the esd database to the ``sql_queries`` added to the context.
    '''
    context_extras = context_processors.debug(request)
    context_extras['ENABLE_BETA_WARNING'] = getattr(settings, 'ENABLE_BETA_WARNING', False)
    if 'debug' in context_extras and context_extras['debug'] \
           and 'esd' in settings.DATABASES:
        from django.db import connections
        esd_queries = connections['esd'].queries
        for q in esd_queries:
            q['db'] = 'esd'
        context_extras['sql_queries']().extend(esd_queries)
    return context_extras


def sitepages(request):
    '''Add a dictonary of
    :class:`~django.contrib.flatpage.models.FlatPage` objects used in
    site navigation to page context under the name ``sitepages``.
    Pages can be accessed by brief nickname (as defined in this
    method), e.g.::

       {{ sitepages.about.url }}
    '''
    pages = FlatPage.objects.all()
    pages_by_url = dict((p.url, p) for p in pages)
    # nickname to be used in the site -> flatpage url
    # alphabetical by url
    nick_urls = {
        'about': '/about/',
        'authors_rights': '/about/authors-rights/',
        'about_profiles': '/about/faculty-profiles/',
        'faq': '/about/faq/',
        'getting_started': '/about/getting-started/',
        'staff': '/about/staff/',
        'terms': '/about/terms-of-use/',

        'howto': '/how-to/',
        'howto_edit_profile': '/how-to/edit-your-profile/',
        'howto_invite': '/how-to/invite-others/',
        'howto_know_rights': '/how-to/know-your-rights/',
        'howto_share': '/how-to/share/',
        'howto_submit': '/how-to/submit/',
        'data_archiving': '/data-archiving/',

        }

    # build a dictionary of nickname -> flatpage object
    nick_pages = {}
    for nick, url in nick_urls.iteritems():
        if url in pages_by_url:
            nick_pages[nick] = pages_by_url[url]

    return {'sitepages': nick_pages}


def site_analytics(request):
    '''Add settings relating to site analytics to the context.
    Currently consists of:

    * GOOGLE_ANALYTICS_ENABLED
    * GOOGLE_SITE_VERIFICATION

    '''
    keys = [
        'GOOGLE_ANALYTICS_ENABLED',
        'GOOGLE_SITE_VERIFICATION',
    ]
    return dict((k, getattr(settings, k, '')) for k in keys)
