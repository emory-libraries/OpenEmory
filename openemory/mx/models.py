from django.db import models
from downtime.models import Period
from django.utils.translation import ugettext_lazy as _

class Banner(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    last_modified = models.DateTimeField(auto_now=True)
    message = models.CharField(max_length=140, help_text=_('The message to be shown in the banner. \nMax length of 140 characters.'))
    period = models.ForeignKey(Period, help_text=_('The downtime associated with this banner. \nUsed to define when to show banner.'))
    days = models.PositiveIntegerField(help_text=_('Number of previous to the downtime period to show the banner.'))
