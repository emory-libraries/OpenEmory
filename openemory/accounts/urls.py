from django.conf.urls.defaults import patterns, include, url
from openemory.accounts import views

urlpatterns = patterns('openemory.accounts.views',
    url(r'^login/$', 'login', name='login'),
    url(r'^logout/$', 'logout', name='logout'),
    # TODO: should be top-level /departments/, not /accounts/departments/
    url(r'^departments/$', views.departments, name='list-departments'),
    url(r'^departments/(?P<id>[A-Z0-9]+)/$', views.view_department,
        name='department'),
    url(r'^(?P<username>[a-zA-Z0-9]+)/$', 'profile', name='profile'),
    url(r'^(?P<username>[a-zA-Z0-9]+)/edit/$', 'edit_profile', name='edit-profile'),
    url(r'^(?P<username>[a-zA-Z0-9]+)/name/$', 'user_name', name='user-name'),
    url(r'^(?P<username>[a-zA-Z0-9]+)/data/$', 'rdf_profile', name='profile-data'),
    url(r'^(?P<username>[a-zA-Z0-9]+)/tags/$', views.profile_tags, name='profile-tags'),
    url(r'^degree/(?P<mode>(institution|name))/autocomplete/$', views.degree_autocomplete,
        name='degree-autocomplete'),                       
    url(r'^grant/autocomplete/$', views.grant_autocomplete, name='grant-autocomplete'),
    url(r'^interests/autocomplete/$', views.interests_autocomplete, name='interests-autocomplete'),
    url(r'^interests/(?P<tag>[a-zA-Z0-9-_]+)/$', views.researchers_by_interest, name='by-interest'),
    url(r'^tags/autocomplete/$', views.tags_autocomplete, name='tags-autocomplete'),
    url(r'^tags/(?P<pid>[^/]+)/$', views.object_tags, name='tags'),
    url(r'^tag/(?P<tag>[a-zA-z0-9-_]+)/$', views.tagged_items, name='tag'),
                       
)
