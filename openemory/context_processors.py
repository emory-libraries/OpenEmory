from django.conf import settings
from django.contrib.flatpages.models import FlatPage
from django.core import context_processors 

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
    if 'debug' in context_extras and context_extras['debug'] \
           and 'esd' in settings.DATABASES:
        from django.db import connections
        esd_queries = connections['esd'].queries
        for q in esd_queries:
            q['db'] = 'esd'
        context_extras['sql_queries'].extend(esd_queries)
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
    nick_urls = {
        'about': '/about/',
        'terms': '/about/terms-of-use/',
        'staff': '/about/staff/',
        'about_submit': '/about/submit/',
        'howto': '/how-to/',
        'howto_submit': '/how-to/submit/',
        'faq': '/about/faq/',
        'authors_rights': '/about/authors-rights/',
        'about_profiles': '/about/faculty-profiles/',
        }

    # build a dictionary of nickname -> flatpage object
    nick_pages = {}
    for nick, url in nick_urls.iteritems():
        if url in pages_by_url:
            nick_pages[nick] = pages_by_url[url]

    return {'sitepages': nick_pages }
    
