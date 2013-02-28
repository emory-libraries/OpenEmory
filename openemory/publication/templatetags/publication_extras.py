# file openemory/publication/templatetags/publication_extras.py
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
