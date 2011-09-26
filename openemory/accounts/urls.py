from django.conf.urls.defaults import patterns, include, url
from openemory.accounts import views

urlpatterns = patterns('',
    url(r'^login/$', views.login, name='login'),
    url(r'^logout/$', views.logout, name='logout'),
    url(r'^(?P<username>[a-zA-Z0-9]+)/$', views.profile, name='profile'),
    url(r'^(?P<username>[a-zA-Z0-9]+)/rdf/$', views.rdf_profile, name='profile-rdf'),
    url(r'^(?P<username>[a-zA-Z0-9]+)/tags/$', views.profile_tags, name='profile-tags'),
    url(r'^interests/autocomplete/$', views.interests_autocomplete, name='interests-autocomplete'),
    url(r'^interests/(?P<tag>[a-zA-Z0-9-]+)/$', views.researchers_by_interest, name='by-interest'),
)
