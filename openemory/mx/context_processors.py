import datetime
from .models import Banner
from downtime.models import Period
from django.utils.timezone import utc


# context processor to add current downtime to the template
def downtime_context(request):
    '''Template context processor: add relevant maintenance banner to site.'''
    banner = Banner.objects.get_deployed().first()
    context = {}
    if banner:
        context.update({'banner': banner})

    site_is_down = Period.objects.is_down()
    if site_is_down:
        context.update({'site_is_down': site_is_down})
    return context
