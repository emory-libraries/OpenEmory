from django.contrib.auth.forms import AuthenticationForm
from django.contrib.contenttypes.models import ContentType
from django.db.models import Count
from taggit.models import Tag
from openemory.accounts.models import Bookmark

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
