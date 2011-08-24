from django.contrib.auth.forms import AuthenticationForm

def authentication_context(request):
    'Context processor to add a login form to every page.'
    if request.user.is_authenticated():
        return {}
    else:
        # TODO: auth form should display login error message when a
        # login attempt fails; binding POST data is not sufficient (?)
        return {'LOGIN_FORM': AuthenticationForm() }
        
