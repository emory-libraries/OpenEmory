import datetime
from django.conf import settings
from django.db import models
from django.utils.timezone import utc
from django.utils.translation import ugettext_lazy as _
from .managers import BannerManager
from downtime.models import Period, PeriodManager
from django.db.models import signals

class DowntimePeriod(Period):
    objects = PeriodManager()

    def __unicode__(self):
        return "Scheduled Downtime: %s to %s" % (self.start_time, self.end_time)


class Banner(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    last_modified = models.DateTimeField(auto_now=True)
    title = models.CharField(max_length=25, help_text=_('The title that will display on the banner. \nMax length of 25 characters.'))
    message = models.CharField(max_length=140, help_text=_('The message to be shown in the banner. \nMax length of 140 characters.'))
    period = models.ForeignKey(DowntimePeriod, help_text=_('The downtime associated with this banner. \nUsed to define when to show banner.'))
    days = models.PositiveIntegerField(help_text=_('Number of days previous to the downtime period to show the banner.'))
    disabled = models.BooleanField(default=False)

    show_on_date = models.DateTimeField(blank=True, null=True, editable=False, help_text=_('The date which the banner will be eligable to be shown.'))

    objects = BannerManager()

    def __unicode__(self):
        return "%s: %s" % (self.title, self.period)

    def save(self, *args, **kwargs):

        self.show_on_date = self.period.start_time - datetime.timedelta(days=self.days)
        super(Banner, self).save(*args, **kwargs)

    @property
    def period_has_started(self):
        return self.period.start_time <= datetime.datetime.now()

    @property
    def downtime(self):
        if self.period.end_time:
            downtime = self.period.end_time - self.period.start_time
            return {'days':downtime.days, 'hours':downtime.seconds//3600}
        else:
            return {'indefinite':True}

    @classmethod
    def do_observe_period_saved(cls, sender, instance, created, **kwargs):
        affected_banners = Banner.objects.filter(period = instance)
        for banner in affected_banners:
            print banner
            banner.save()
        pass

signals.post_save.connect( Banner.do_observe_period_saved, sender=DowntimePeriod )
