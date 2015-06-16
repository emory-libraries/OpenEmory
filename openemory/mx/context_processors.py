import datetime
from .models import Banner
from django.utils.timezone import utc

# context processor to add current site to the template
def banner_context(request):

    banners = Banner.objects.all()
    for banner in banners:
        if banner.is_active:
            return {'banner': banner}

    return {'banner': None}
