from django.contrib.auth.forms import AuthenticationForm
from django.db.models import Count
from taggit.models import Tag

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
        tags = Tag.objects.filter(bookmark__user=request.user).annotate(count=Count('bookmark__user')).order_by('-count')
    else:
        tags = Tag.objects.none()

    return {'tags': tags}
