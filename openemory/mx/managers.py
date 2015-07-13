import datetime
from django.db import models
from django.db.models import Q
from django.conf import settings
from django.utils.timezone import utc


class BannerQuerySet(models.query.QuerySet):

    def active(self):
        """
        Returns banner objects that are not marked as disabled
        or have a period that is not enabled.
        Banners that are marked as disabled, or reference
        a disabled period, are not active.
        """
        return self.filter(disabled=False, period__enabled=True)

    def first(self):
        """
        Returns the first object matched by the queryset.
        Defined here for Django <1.6 support.
        """
        if self.count():
            return self[0]

        return self

    def deployed(self):
        """
        Returns banner objects that would be visible based on their show_on_date
        and period end_time.
        """
        if getattr(settings, 'USE_TZ', False):
            now = datetime.datetime.utcnow().replace(tzinfo=utc)
        else:
            now = datetime.datetime.now()
        query_show = Q(show_on_date__lte=now) & (Q(period__end_time__gte=now) | Q(period__end_time=None))

        banners = self.filter(query_show)

        # If banners that would be visible do not have a end_time,
        # the site will be in maintenance mode for an indetermined
        # amount of time. Therfore, calculations on downtime
        # cannot be made. Because this is a different scenario
        # from an empty query, we need to specifically identify
        # indefinite periods of downtime.

        indefinite = banners.filter(period__end_time=None)

        if indefinite:
            return indefinite

        # If there are no indefinite downtime scenarios,
        # return the queryset ordered by end_time in reversed
        # order, so times further in the future are first.

        return banners.order_by('-period__end_time')


class BannerManager(models.Manager):

    def get_queryset(self):
        return BannerQuerySet(self.model, using=self._db)

    def get_active(self):
        return self.get_queryset().active()

    def get_deployed(self):
        return self.get_queryset().active().deployed()
