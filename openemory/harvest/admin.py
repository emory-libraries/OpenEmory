from django.contrib import admin
from openemory.harvest.models import HarvestRecord

class HarvestRecordAdmin(admin.ModelAdmin):
    date_hierarchy = 'harvested'
    list_display = ('pmcid', 'title', 'fulltext', 'status', 'harvested')
    list_filter = ('status', 'fulltext', 'harvested')

admin.site.register(HarvestRecord, HarvestRecordAdmin)
