'''
Custom template tags and filters for displaying Publication content.

'''
from django import template
from django.template.defaultfilters import stringfilter
from openemory.util import pmc_access_url

register = template.Library()


@register.filter
@stringfilter
def pmc_url(value):
    '''Template tag filter go generate a direct link to this PubMed
    Central article, based on a numeric PubMed Central ID.'''
    try:
        value = int(value)
    except ValueError:
        return u''
    return pmc_access_url(value)


@register.filter
@stringfilter
def parse_author(stored_value):
    '''Parse author data out of a solr parsed_author field.'''
    netid, rest = stored_value.split(':', 1)
    return {
        'netid': netid,
        'name': rest,
    }
