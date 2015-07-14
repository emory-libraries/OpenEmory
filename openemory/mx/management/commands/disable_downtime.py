from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils.timezone import utc
import datetime

from downtime.models import Period


class Command(BaseCommand):
    """
    `disable_downtime` command sets enabled to False for all active period objects.
    This command is useful if you want to bring a site up even during scheduled maintenance.
    """
    help = 'Disables all active downtime periods.'

    def handle(self, *args, **options):
        objects = Period.objects.active()

        # Check to see if there are any Period objects are in the 'down' status
        if not objects:
            self.stdout.write('Warning: All downtime periods are already disabled!')
            return False

        for obj in objects:
            obj.enabled = False
            obj.save()

        self.stdout.write('Success! All downtime periods have been disabled.')
