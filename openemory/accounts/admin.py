from django.contrib import admin
from openemory.accounts.models import Bookmark,  Degree


class BookmarkAdmin(admin.ModelAdmin):
    list_display = ('user', 'pid', 'display_tags')

admin.site.register(Bookmark, BookmarkAdmin)

class DegreeAdmin(admin.ModelAdmin):
    list_display = ('holder', 'name', 'institution', 'year')
    
admin.site.register(Degree, DegreeAdmin)
