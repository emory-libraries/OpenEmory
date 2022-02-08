# file openemory/accounts/context_processors.py
# 
#   Copyright 2010 Emory University General Library
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

from datetime import datetime
from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.contenttypes.models import ContentType
from django.contrib.sessions.models import Session
from django.db.models import Count
from django.utils.translation import ugettext_lazy as _
from taggit.models import Tag
from openemory.accounts.models import Bookmark, EsdPerson
from openemory.util import solr_interface


# really? do we have to extend the auth form just for style/design?
# FIXME: look for a better solution
class LocalAuthenticationForm(AuthenticationForm):
    """
    Base class for authenticating users. Extend this to get a form that accepts
    username/password logins.
    """
    username_help_text ='username'
    username = forms.CharField(label=_("Username"), max_length=30, initial=username_help_text,
                               widget=forms.TextInput(attrs={'class': 'text', 'help_text': username_help_text}))
    password = forms.CharField(label=_("Password"), widget=forms.PasswordInput(attrs={'id': 'password', 'class': 'text', 'autocomplete': "off"}))
    #This fields is swapped back and forth on focus / blur with
    # the real password field so that initial text can be displayed / cleared
    password_text = forms.CharField(label=_("Password"), widget=forms.TextInput(attrs={'id': 'password-clear', 'value': 'password',
                                                                                       'class': 'text', 'autocomplete': "off"}))


def authentication_context(request):
    'Context processor to add a login form to every page.'
    if request.user.is_authenticated:
        return {}
    else:
        # TODO: auth form should display login error message when a
        # login attempt fails; binding POST data is not sufficient (?)
        return {'LOGIN_FORM': LocalAuthenticationForm() }
        

def user_tags(request):
    '''Context processor to add the tags for the current user to every page.'''
    if request.user.is_authenticated:
        # taggit v0.9.3 (the current version as of 2011-12-07) doesn't
        # recognize that filtering Tag objects on bookmark__user implies
        # that we only want tags for bookmarks. so here we have to make that
        # explicit by using awkward syntax to filter on content_type.
        bookmark_type =  ContentType.objects.get_for_model(Bookmark)
        tags = Tag.objects.filter(taggit_taggeditem_items__content_type=bookmark_type,
                                  bookmark__user=request.user).annotate(count=Count('bookmark__user')).order_by('-count')
    else:
        tags = Tag.objects.none()

    return {'tags': tags}


def statistics(request):
    '''`Template context processor
    <https://docs.djangoproject.com/en/dev/ref/settings/#template-context-processors>`_
    to add account and session statistics to page context under the name
    ACCOUNT_STATISTICS. The object currently has only one property:
    ``total_users``.'''

    solr_query = solr_interface().query() \
                                 .filter(record_type=EsdPerson.record_type) \
                                 .paginate(rows=0)
    faculty_count = solr_query.execute().result.numFound
    stats = { 'total_users': faculty_count }

    return { 'ACCOUNT_STATISTICS': stats }
