# file openemory/publication/admin.py
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
from django import forms
from openemory.publication.models import ArticleStatistics, FeaturedArticle, License, LastRun

class ArticleStatisticsAdmin(admin.ModelAdmin):
    list_display = ('pid', 'year', 'quarter', 'num_views', 'num_downloads')
    list_filter = ('year',)
    search_fields = ('pid', 'year')
    # NOTE: may want to make these fields read-only in admin site...

class LicenseAdminForm(forms.ModelForm):
  class Meta:
    model = License
    fields = ['title', 'short_name', 'url', 'version']
    search_fields = ('title', 'short_name')
    widgets = {
      'version': forms.TextInput(attrs={'size':5}),
      'short_name': forms.TextInput(attrs={'size':30})
    }



class LicenseAdmin(admin.ModelAdmin):
    form = LicenseAdminForm
    list_display = ('__unicode__', 'url', 'version')

class LastRunAdmin(admin.ModelAdmin):
    list_display = ('name', 'start_time')
    readonly_fields = ('name',)
    fields = ['name', 'start_time']
    list_editable = ('start_time',)




admin.site.register(ArticleStatistics, ArticleStatisticsAdmin)
admin.site.register(License, LicenseAdmin)
admin.site.register(FeaturedArticle)
admin.site.register(LastRun, LastRunAdmin)
