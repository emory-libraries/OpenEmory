'''

Utilities for dealing with authentiation & authorization in
:mod:`openemory`.

Includes variant permisson-checing decorators without the redirect
logic used in the standard Django versions, since :mod:`openemory`
includes a login form on every page.

'''


from functools import wraps

from django.http import HttpResponse
from django.template import RequestContext
from django.template.loader import get_template
from django.utils.decorators import available_attrs


def user_passes_test_401_or_403(test_func):
    """
    View decorator that checks to see if the user passes the specified test.
    See :meth:`django.contrib.auth.decorators.user_passes_test`.

    Anonymous users will be given a 401 error, which will render the
    **401.html** template (which is expected to include the login
    form); logged in users that fail the test will be given a 403
    error.  In the case of a 403, the function will render the
    **403.html** template.
    """
    def decorator(view_func):
        @wraps(view_func, assigned=available_attrs(view_func))
        def _wrapped_view(request, *args, **kwargs):
            try:
                passes = test_func(request.user)
            except TypeError:
                # allow test functions access to view arguments,
                # but only pass if the function fails without them
                passes = test_func(request.user, *args, **kwargs)
                
            if passes:
                # if the test passes, return the view function normally
                return view_func(request, *args, **kwargs)

            elif not request.user.is_authenticated():
                # if the test fails and user is not authenticated
                code = 401
                text = 'Not Authorized'
            else:
                # test fails and user is already authenticated
                code = 403
                text = 'Permission Denied'

            # send a plain-text response to ajax requests
            if request.is_ajax():
                return HttpResponse(text, mimetype='text/plain',
                                    status=code)
                
            tpl = get_template('%s.html' % code)
            return HttpResponse(tpl.render(RequestContext(request)),
                                status=code)
        return _wrapped_view
    return decorator

def permission_required(perm):
    """
    Decorator for views that checks whether a user has a particular
    permission enabled, rendering a 401 or 403 as necessary.
    Convenience wrapper for
    :meth:`~openemory.accounts.auth.user_passes_test_401_or_403`.

    See :meth:`django.contrib.auth.decorators.permission_required`.
    """
    return user_passes_test_401_or_403(lambda u: u.has_perm(perm))


def login_required(function=None):
    """
    Decorator for views that checks that the user is logged in,
    rendering a 401 or 403 template as appropriate.  See
    :meth:`~openemory.accounts.auth.user_passes_test_401_or_403`.
    """
    actual_decorator = user_passes_test_401_or_403(lambda u: u.is_authenticated())
    if function:
        return actual_decorator(function)
    return actual_decorator


def require_self_or_admin(function=None):
    '''Check if user is logged and matches the specified username,
    is a superuser, or belongs to the SiteAdmin group.

    First parameter to the wrapped view must be the username to
    compare against.  For example::

	@require_self_or_admin
	def edit_profile(request, username):
            ...

    
    '''
    
    def test_self_or_admin(user, username, *args, **kwargs):
        return (user.is_authenticated() and user.username == username) \
               or user.is_superuser \
               or user.groups.filter(name='Site Admin').count()

    actual_decorator = user_passes_test_401_or_403(test_self_or_admin)
    if function:
        return actual_decorator(function)
    return actual_decorator

