__version_info__ = (0, 1, 0, 'dev')

# Dot-connect all but the last. Last is dash-connected if not None.
__version__ = '.'.join([ str(i) for i in __version_info__[:-1] ])
if __version_info__[-1] is not None:
    __version__ += ('-%s' % (__version_info__[-1],))

# context processor to add version to the template environment
def version_context(request):
    return { 'SW_VERSION': __version__ }

# context processor to add a login form to every page
# FIXME: this probably belongs somewhere else once we get actual
# authentication set up.
def authentication_context(request):
    from django.conf import settings
    from django.contrib.auth.forms import AuthenticationForm
    if request.user.is_authenticated():
        return {}
    else:
        return { 'LOGIN_FORM': AuthenticationForm() }
