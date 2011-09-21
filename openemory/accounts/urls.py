from django.conf.urls.defaults import patterns, include, url
from openemory.accounts import views

urlpatterns = patterns('',
    url(r'^login/$', views.login, name='login'),
    url(r'^logout/$', views.logout, name='logout'),
    url(r'^(?P<username>[a-zA-Z0-9]+)/$', views.profile, name='profile'),
    url(r'^(?P<username>[a-zA-Z0-9]+)/rdf/$', views.rdf_profile, name='profile-rdf'),
    url(r'^(?P<username>[a-zA-Z0-9]+)/tags/$', views.profile_tags, name='profile-tags'),
)
