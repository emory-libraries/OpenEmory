from django.contrib import admin
from openemory.accounts.models import Bookmark, Degree, Position, \
        UserProfile


class BookmarkAdmin(admin.ModelAdmin):
    list_display = ('user', 'pid', 'display_tags')

admin.site.register(Bookmark, BookmarkAdmin)

class DegreeAdmin(admin.ModelAdmin):
    # TODO: inline this in UserProfile admin
    list_display = ('holder', 'name', 'institution', 'year')
    
admin.site.register(Degree, DegreeAdmin)

class PositionAdmin(admin.ModelAdmin):
    # TODO: inline this in UserProfile admin
    list_display = ('holder', 'name')

admin.site.register(Position, PositionAdmin)
