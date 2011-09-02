from django.conf.urls.defaults import patterns, include, url
from openemory.harvest import views

urlpatterns = patterns('',
    url(r'^queue/$', views.queue, name='queue'),
)
