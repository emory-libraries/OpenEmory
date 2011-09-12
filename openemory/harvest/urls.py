from django.conf.urls.defaults import patterns, include, url
from openemory.harvest import views

urlpatterns = patterns('',
    url(r'^queue/$', views.queue, name='queue'),
    url(r'^records/(?P<id>[0-9]+)/$', views.record, name='record'),
)
