from django.contrib import admin
from .models import Banner, DowntimePeriod

admin.site.register(DowntimePeriod)
admin.site.register(Banner)
