import datetime
from django.db import models
from django.db.models import Q
from django.conf import settings
from django.utils.timezone import utc

class BannerQuerySet(models.query.QuerySet):

    def active(self):
        return self.filter(disabled=False, period__enabled=True)

    def first(self):
        if self.count():
            return self[0]

        return self

    def deployed(self):
        if getattr(settings, 'USE_TZ', False):
            now = datetime.datetime.utcnow().replace(tzinfo=utc)
        else:
            now = datetime.datetime.now()
        query_show = Q(show_on_date__lte=now) & (Q(period__end_time__gte=now) | Q(period__end_time=None))

        banners = self.filter(query_show)

        indefinite = banners.filter(period__end_time=None)

        if indefinite:
            return indefinite

        return banners.order_by('-period__end_time')


class BannerManager(models.Manager):

    def get_queryset(self):
        return BannerQuerySet(self.model, using=self._db)

    def get_active(self):
        return self.get_queryset().active()

    def get_deployed(self):
        return self.get_queryset().active().deployed()
