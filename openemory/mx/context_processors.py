import datetime
from .models import Banner
from django.utils.timezone import utc

# context processor to add current downtime to the template
def downtime_context(request):
    banners = Banner.objects.get_active()

    banner = Banner.objects.get_deployed()

    if banner:
        banner = banner[0]
        return {'banner': banner}

    return {'banner': None}
