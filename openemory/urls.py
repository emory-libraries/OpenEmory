from django.conf.urls.defaults import patterns, include, url
from django.views.generic.simple import direct_to_template

urlpatterns = patterns('',
    url(r'^$', direct_to_template, {'template': 'index.html'}, name='site-index'),

# basic django auth. TODO: move to accounts/profiles module once that exists
    url(r'^login/', 'django.contrib.auth.views.login', name='login'),
    url(r'^logout/', 'django.contrib.auth.views.logout', name='logout',
            kwargs={'next_page': '..' }), # .. here because we can't reverse(site-index)
)
