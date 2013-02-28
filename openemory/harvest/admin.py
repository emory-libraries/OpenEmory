# file openemory/harvest/admin.py
# 
#   Copyright 2010 Emory University General Library
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

from django.contrib import admin
from openemory.harvest.models import HarvestRecord

class HarvestRecordAdmin(admin.ModelAdmin):
    date_hierarchy = 'harvested'
    list_display = ('pmcid', 'title', 'fulltext', 'status', 'harvested')
    list_filter = ('status', 'fulltext', 'harvested')
    list_editable = ('status',)

admin.site.register(HarvestRecord, HarvestRecordAdmin)
