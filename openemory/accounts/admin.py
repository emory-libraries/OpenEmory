# file openemory/accounts/admin.py
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
from django.contrib.flatpages.models import FlatPage
from django.contrib.flatpages.admin import FlatPageAdmin as FlatPageAdminDefault
from django.db.models.fields import TextField
from django.forms.widgets import Textarea
from eullocal.django.emory_ldap.admin import EmoryLDAPUserProfileAdmin
from openemory.accounts.models import Bookmark, Degree, Position, \
        UserProfile, Announcement


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


class UserProfileAdmin(EmoryLDAPUserProfileAdmin):
    '''Extend
    :class:`eullocal.django.emory_ldap.admin.EmoryLDAPUserProfileAdmin`
    to customize for locally added profile fields and functionality.
    '''
    list_display = ('__unicode__', 'full_name', 'edit_user',
                    'show_suppressed', 'nonfaculty_profile')
    list_filter = ('show_suppressed', 'nonfaculty_profile')
    list_editable = ('nonfaculty_profile', )
    search_fields = ('user__username', 'full_name', 'user__last_name', 'user__first_name')

# unregister eullocal user profile admin
admin.site.unregister(UserProfile)
admin.site.register(UserProfile, UserProfileAdmin)

# patch a method onto the FlatPage model to link to view from list display


# FlatPage.view_on_site = view_on_site

# customizing flatpages admin here because we don't have a separate app for it
class FlatPageAdmin(FlatPageAdminDefault):
    
    def view_on_site(self,fp):
        return '<a href="%(url)s" target="_top">%(url)s</a>' % \
                         {'url': fp.get_absolute_url()}
    
    list_display = ('title', 'view_on_site')
    view_on_site.allow_tags = True
    list_display_links = ('title', )
    # list_display = ('title',)
    search_fields = ('url', 'title', 'content')
    fieldsets = (
        (None, {'fields': ('url', 'title', 'content', 'sites')}),
        (('Advanced options'), {
            'classes': ('collapse', ),
            'fields': (
                'enable_comments',
                'registration_required',
                'template_name',
            ),
        }),
    )
    class Media:
        js = ('js/tiny_mce/tiny_mce.js',
              'js/tiny_mce/textareas.js',)


# unregister default flatpages admin and re-register customized version
admin.site.unregister(FlatPage)
admin.site.register(FlatPage, FlatPageAdmin)


class AnnouncementAdmin(admin.ModelAdmin):
    '''Extend :class:`admin.ModelAdmin`
    to customize admin page for :class:`~openemory.accounts.models.Announcement`
    objects.
    '''
    list_display = ('id', 'active', 'message', 'start', 'end')
    list_editable = ('active', 'message', 'start', 'end')
    search_fields = ['message']
    list_display_links = ['id']
    formfield_overrides = {
        TextField: {'widget': Textarea(attrs={'rows':3, 'cols':30})}
    }

admin.site.register(Announcement, AnnouncementAdmin)
