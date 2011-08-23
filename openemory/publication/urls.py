from django.conf.urls.defaults import patterns, include, url
from openemory.publication import views

urlpatterns = patterns('',
    url(r'^upload/$', views.upload, name='upload'),
    url(r'^(?P<pid>[^/]+)/pdf/$', views.download_pdf, name='pdf'),
)
