from datetime import datetime
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.contenttypes.models import ContentType
from django.contrib.sessions.models import Session
from django.db.models import Count
from taggit.models import Tag
from openemory.accounts.models import Bookmark, EsdPerson
from openemory.util import solr_interface

def authentication_context(request):
    'Context processor to add a login form to every page.'
    if request.user.is_authenticated():
        return {}
    else:
        # TODO: auth form should display login error message when a
        # login attempt fails; binding POST data is not sufficient (?)
        return {'LOGIN_FORM': AuthenticationForm() }
        

def user_tags(request):
    '''Context processor to add the tags for the current user to every page.'''
    if request.user.is_authenticated():
        # taggit v0.9.3 (the current version as of 2011-12-07) doesn't
        # recognize that filtering Tag objects on bookmark__user implies
        # that we only want tags for bookmarks. so here we have to make that
        # explicit by using awkward syntax to filter on content_type.
        bookmark_type =  ContentType.objects.get_for_model(Bookmark)
        tags = Tag.objects.filter(taggit_taggeditem_items__content_type=bookmark_type,
                                  bookmark__user=request.user).annotate(count=Count('bookmark__user')).order_by('-count')
    else:
        tags = Tag.objects.none()

    return {'tags': tags}


def statistics(request):
    '''`Template context processor
    <https://docs.djangoproject.com/en/dev/ref/settings/#template-context-processors>`_
    to add account and session statistics to page context under the name
    ACCOUNT_STATISTICS. The object has two properties: ``total_users`` and
    ``current_users``.'''

    solr_query = solr_interface().query() \
                                 .filter(record_type=EsdPerson.record_type) \
                                 .paginate(rows=0)
    faculty_count = solr_query.execute().result.numFound
    stats = dict(total_users=faculty_count)

    session_qs = Session.objects.filter(expire_date__gt=datetime.now())
    active_sessions = session_qs.count()
    stats['current_users'] = active_sessions

    return { 'ACCOUNT_STATISTICS': stats }
