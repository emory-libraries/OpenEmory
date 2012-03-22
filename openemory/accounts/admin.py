from django.contrib import admin
from django.contrib.flatpages.models import FlatPage
from django.contrib.flatpages.admin import FlatPageAdmin as FlatPageAdminDefault
from eullocal.django.emory_ldap.admin import EmoryLDAPUserProfileAdmin
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
def view_on_site(fp):
    return '<a href="%(url)s" target="_top">%(url)s</a>' % \
                     {'url': fp.get_absolute_url()}
FlatPage.view_on_site = view_on_site

# customizing flatpages admin here because we don't have a separate app for it
class FlatPageAdmin(FlatPageAdminDefault):
    list_display = ('title', 'view_on_site')
    list_display_links = ('title', )
    search_fields = ('url', 'title', 'content')
    view_on_site.allow_tags = True
    class Media:
        js = ('js/tiny_mce/tiny_mce.js',
              'js/tiny_mce/textareas.js',)

# unregister default flatpages admin and re-register customized version
admin.site.unregister(FlatPage)
admin.site.register(FlatPage, FlatPageAdmin)
