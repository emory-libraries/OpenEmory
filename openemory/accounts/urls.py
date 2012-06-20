from django.conf.urls.defaults import patterns, include, url
from openemory.accounts import views

urlpatterns = patterns('openemory.accounts.views',
    url(r'^login/$', 'login', name='login'),
    url(r'^logout/$', 'logout', name='logout'),
    # department browse
    url(r'^profiles/departments/$', views.departments, name='list-departments'),
    url(r'^profiles/departments/(?P<id>[A-Z0-9]+)/$', views.view_department,
        name='department'),
    # profile pages
    url(r'^profiles/autocomplete/$', views.faculty_autocomplete,
        name='faculty-autocomplete'),
    url(r'^profiles/positions/autocomplete/$',
        views.position_autocomplete ,name='position-autocomplete'),
    url(r'^profiles/(?P<username>[a-zA-Z0-9]+)/$', 'profile', name='profile'),
    # dashboard tab content pages
    url(r'^profiles/(?P<username>[a-zA-Z0-9]+)/summary/$', 'dashboard_summary', name='dashboard'),
    url(r'^profiles/(?P<username>[a-zA-Z0-9]+)/documents/$', 'dashboard_documents', name='documents'),
    url(r'^profiles/(?P<username>[a-zA-Z0-9]+)/info/$', 'public_profile', name='dashboard-profile'),
    url(r'^profiles/(?P<username>[a-zA-Z0-9]+)/edit/$', 'public_profile', name='edit-profile'),
                       
    url(r'^profiles/(?P<username>[a-zA-Z0-9]+)/data/$', 'rdf_profile', name='profile-data'),
    url(r'^profiles/(?P<username>[a-zA-Z0-9]+)/tags/$', views.profile_tags, name='profile-tags'),
    # profile-specific auto-complete views
    url(r'^profiles/degrees/(?P<mode>(institution|name))/autocomplete/$',
        views.degree_autocomplete, name='degree-autocomplete'),                       
    url(r'^profiles/grants/autocomplete/$', views.grant_autocomplete,
        name='grant-autocomplete'),
    url(r'^profiles/interests/autocomplete/$', views.interests_autocomplete,
        name='interests-autocomplete'),
    url(r'^profiles/interests/(?P<tag>[a-zA-Z0-9-_]+)/$', views.researchers_by_interest,
        name='by-interest'),

    # article tagging views
    url(r'^tags/autocomplete/$', views.tags_autocomplete, name='tags-autocomplete'),
    url(r'^tags/(?P<pid>[^/]+)/$', views.object_tags, name='tags'),
    url(r'^tag/(?P<tag>[a-zA-z0-9-_]+)/$', views.tagged_items, name='tag'),

    # admin dashboard
    url(r'^admin/$', views.admin_dashboard, name='admin-dashboard'),

)
