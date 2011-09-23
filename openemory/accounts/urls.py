from django.conf.urls.defaults import patterns, include, url
from openemory.accounts import views

urlpatterns = patterns('openemory.accounts.views',
    url(r'^login/$', 'login', name='login'),
    url(r'^logout/$', 'logout', name='logout'),
    url(r'^(?P<username>[a-zA-Z0-9]+)/$', 'profile', name='profile'),
    url(r'^(?P<username>[a-zA-Z0-9]+)/data/$', 'rdf_profile', name='profile-data'),
)
