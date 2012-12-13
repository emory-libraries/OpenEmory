from django.contrib import admin
from django import forms
from openemory.publication.models import ArticleStatistics, FeaturedArticle, License

class ArticleStatisticsAdmin(admin.ModelAdmin):
    list_display = ('pid', 'year', 'num_views', 'num_downloads')
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
      'short_name': forms.TextInput(attrs={'size':10})
    }



class LicenseAdmin(admin.ModelAdmin):
    form = LicenseAdminForm
    list_display = ('__unicode__', 'url', 'version')

admin.site.register(ArticleStatistics, ArticleStatisticsAdmin)
admin.site.register(License, LicenseAdmin)
admin.site.register(FeaturedArticle)
