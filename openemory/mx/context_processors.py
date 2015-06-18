import datetime
from .models import Banner, DowntimePeriod
from django.utils.timezone import utc

# context processor to add current downtime to the template
def downtime_context(request):
    '''Template context processor: add relevant maintenance banner to site.'''
    banner = Banner.objects.get_deployed()
    if banner:
        banner = banner[0]
        return {'banner': banner}

    site_is_down = DowntimePeriod.objects.is_down()
    return {'site_is_down': site_is_down}
