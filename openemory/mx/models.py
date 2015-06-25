import datetime
from django.conf import settings
from django.db import models
from django.utils.timezone import utc
from django.utils.translation import ugettext_lazy as _
from .managers import BannerManager
from downtime.models import Period
from django.db.models import signals


# MX Banners
class Banner(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    last_modified = models.DateTimeField(auto_now=True)
    title = models.CharField(max_length=25, help_text=_('The title that will display on the banner. \nMax length of 25 characters.'))
    message = models.CharField(max_length=140, help_text=_('The message to be shown in the banner. \nMax length of 140 characters.'))
    period = models.ForeignKey(Period, help_text=_('The downtime associated with this banner. \nUsed to define when to show banner.'))
    days = models.PositiveIntegerField(help_text=_('Number of days previous to the downtime period to show the banner.'))
    disabled = models.BooleanField(default=False)

    show_on_date = models.DateTimeField(blank=True, null=True, editable=False, help_text=_('The date which the banner will be eligable to be shown.'))

    objects = BannerManager()

    class Meta:
        verbose_name = "Downtime Banner"
        verbose_name_plural = "Downtime Banners"

    def __unicode__(self):
        """
        Returns unicode for Django instance references.
        """
        return "%s: %s" % (self.title, self.period)

    def save(self, *args, **kwargs):
        """
        Update the show_on_date of the banner object when saved.
        `show_on_date` is calculated on the period.start_time and days;
        it is used for querying the appropriate banner to display by datetime.
        """
        self.show_on_date = self.period.start_time - datetime.timedelta(days=self.days)
        super(Banner, self).save(*args, **kwargs)

    @property
    def period_has_started(self):
        """
        Returns True if the start_time of the associated period occurs in the
        past based on the current time.
        """
        return self.period.start_time <= datetime.datetime.now()

    @property
    def downtime(self):
        """
        Returns the duration of the scheduled downtime in terms of days and hours
        by subtracting the period's end_time from the start_time.
        If no end_time is defined, returns indefinite.
        """
        duration = {}
        if self.period.end_time:
            downtime= (self.period.end_time - self.period.start_time)
            duration.update({'days': downtime.days, 'hours': downtime.seconds //3600})
        else:
            duration.update({'indefinite': True})
        return duration

    @classmethod
    def do_observe_period_saved(cls, sender, instance, created, **kwargs):
        """
        Saves banner objects that are affected by period updates.
        (Referenced periods help define times for start, end, and display.)
        """
        affected_banners = Banner.objects.filter(period=instance)
        for banner in affected_banners:
            banner.save()
        pass

signals.post_save.connect(Banner.do_observe_period_saved, sender=Period)
