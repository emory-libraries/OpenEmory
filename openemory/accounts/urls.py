from django.conf.urls.defaults import patterns, include, url
from openemory.accounts import views

urlpatterns = patterns('openemory.accounts.views',
    url(r'^login/$', 'login', name='login'),
    url(r'^logout/$', 'logout', name='logout'),
    url(r'^(?P<username>[a-zA-Z0-9]+)/$', 'profile', name='profile'),
    url(r'^(?P<username>[a-zA-Z0-9]+)/name/$', 'user_name', name='user-name'),
    url(r'^(?P<username>[a-zA-Z0-9]+)/data/$', 'rdf_profile', name='profile-data'),
    url(r'^(?P<username>[a-zA-Z0-9]+)/tags/$', views.profile_tags, name='profile-tags'),
    url(r'^interests/autocomplete/$', views.interests_autocomplete, name='interests-autocomplete'),
    url(r'^interests/(?P<tag>[a-zA-Z0-9-_]+)/$', views.researchers_by_interest, name='by-interest'),
    url(r'^tags/autocomplete/$', views.tags_autocomplete, name='tags-autocomplete'),
    url(r'^tags/(?P<pid>[^/]+)/$', views.object_tags, name='tags'),
    url(r'^tag/(?P<tag>[a-zA-z0-9-_]+)/$', views.tagged_items, name='tag'),
)
