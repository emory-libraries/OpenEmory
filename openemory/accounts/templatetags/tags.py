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
    if not pid or not user.is_authenticated():
        return []
    try:
        bk = Bookmark.objects.get(pid=pid, user=user)
        return bk.tags.all()
    except (ObjectDoesNotExist, MultipleObjectsReturned):
        return []
    
