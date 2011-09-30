from django.contrib import admin
from openemory.accounts.models import Bookmark


class BookmarkAdmin(admin.ModelAdmin):
    list_display = ('user', 'pid', 'display_tags')

admin.site.register(Bookmark, BookmarkAdmin)
