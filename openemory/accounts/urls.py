from django.conf.urls.defaults import patterns, include, url
from openemory.accounts import views

urlpatterns = patterns('',
    url(r'^login/$', views.login, name='login'),
    url(r'^logout/$', views.logout, name='logout'),
    url(r'^(?P<username>[a-z0-9]+)/$', views.profile, name='profile'),
)
