from django.core.urlresolvers import reverse
from django.contrib.auth import views as authviews

def logout(request):
    return authviews.logout(request, next_page=reverse('site-index'))
