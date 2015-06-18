# Based on django-downtime downtime_end command
# Overriding this customization until bugfix is made in django-downtime

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils.timezone import utc
import datetime

from eultheme.models import DowntimePeriod

class Command(BaseCommand):
    help = 'End downtime after finished maintenance.'

    def handle(self, *args, **options):
        objects = DowntimePeriod.objects.is_deployment()

        # Check to see if there are any DowntimePeriod objects in 'deployement'
        if not objects:
            objects = DowntimePeriod.objects.is_down()

        # Check to see if there are any DowntimePeriod objects are in the 'down' status
        if not objects:
            self.stdout.write('Warning: Couldn\'t find any applicable downtime objects. Check to see if the site accessible?')
            return False

        if getattr(settings, 'USE_TZ', False):
            _now = datetime.datetime.utcnow().replace(tzinfo=utc)
        else:
            _now = datetime.datetime.now()
        for obj in objects:
            obj.end_time = _now
            obj.save()

        self.stdout.write('Successfully ended downtime! The site should now be accessible.')
