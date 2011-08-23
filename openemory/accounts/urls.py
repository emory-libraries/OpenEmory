from django.conf.urls.defaults import patterns, include, url
from eulfedora.views import login_and_store_credentials_in_session
from openemory.accounts import views

urlpatterns = patterns('',
    url(r'^login/', login_and_store_credentials_in_session, name='login'),
    url(r'^logout/', views.logout, name='logout')
)
