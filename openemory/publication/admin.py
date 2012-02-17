from django.contrib import admin
from openemory.publication.models import ArticleStatistics

class ArticleStatisticsAdmin(admin.ModelAdmin):
    list_display = ('pid', 'year', 'num_views', 'num_downloads')
    list_filter = ('year',)
    search_fields = ('pid', 'year')
    # NOTE: may want to make these fields read-only in admin site...

admin.site.register(ArticleStatistics, ArticleStatisticsAdmin)
