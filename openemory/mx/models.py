import datetime
from django.conf import settings
from django.db import models
from django.utils.timezone import utc
from django.utils.translation import ugettext_lazy as _
from downtime.models import Period


class Banner(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    last_modified = models.DateTimeField(auto_now=True)
    title = models.CharField(max_length=25, help_text=_('The title that will display on the banner. \nMax length of 25 characters.'))
    message = models.CharField(max_length=140, help_text=_('The message to be shown in the banner. \nMax length of 140 characters.'))
    period = models.ForeignKey(Period, help_text=_('The downtime associated with this banner. \nUsed to define when to show banner.'))
    days = models.PositiveIntegerField(help_text=_('Number of days previous to the downtime period to show the banner.'))
    disabled = models.BooleanField(default=False)

    @property
    def is_active(self):
        """
        Checks if the Banner object should be visible based on the associated period
        and the set number of days before the start time. 
        Returns an object with the calculated days and hours of the expected downtime.
        """
        if self.disabled is True:
            return False

        if getattr(settings, 'USE_TZ', False):
            now = datetime.datetime.utcnow().replace(tzinfo=utc)
        else:
            now = datetime.datetime.now()

        start_show = self.period.start_time - datetime.timedelta(days=self.days)

        if start_show <= now and (self.period.end_time >= now or self.period.end_time == None):
            downtime = None
            if self.period.end_time:
                downtime = self.period.end_time - self.period.start_time
            return {'downtime':{'days':downtime.days, 'hours':downtime.seconds//3600}}

        return False
