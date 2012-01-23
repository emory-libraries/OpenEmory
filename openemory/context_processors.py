from django.conf import settings
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
