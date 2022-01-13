# file openemory/accounts/templatetags/tags.py
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

from django import template
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned

from openemory.accounts.models import Bookmark

register = template.Library()

@register.filter
def tags_for_user(object, user):
    '''Return a list of :class:`~taggit.models.Tag` objects for the
    specified object and user.  Returns an empty list if the user is
    not authenticated, object does not have a pid, or no
    :class:`~openemory.accounts.models.Bookmark` record is found.
    Example use::

       {% for tag in article|tags_for_user:user %}
         {{ tag.name }}{% if not forloop.last %}, {% endif %}
       {% endfor %}

    :param object: tagged, bookmarked object - can be anything with a
    	pid attribute or a dictionary with a pid value (e.g., a
    	:class:`~eulfedora.model.DigitalObject` or a :mod:`sunburnt`
    	Solr result)
    :param user: the user whose tags should be retrieved
    
    '''
    
    pid = getattr(object, 'pid', None)
    if pid is None and 'pid' in object:
        pid = object['pid']
    if not pid or not user.is_authenticated:
        return []
    try:
        bk = Bookmark.objects.get(pid=pid, user=user)
        return bk.tags.all()
    except (ObjectDoesNotExist, MultipleObjectsReturned):
        return []
    
