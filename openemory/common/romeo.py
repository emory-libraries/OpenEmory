# file openemory/common/romeo.py
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

'''SHERPA/RoMEO API access

This module provides access to the `SHERPA/RoMEO`_ publisher copyright
policy database through its `web API`_. The API provides seven basic
search types, which are exposed here as functions:

 * :func:`search_publisher_name`
 * :func:`search_publisher_id`
 * :func:`search_journal_title`
 * :func:`search_journal_followup`
 * :func:`search_journal_issn`
 * :func:`all_publishers`
 * :func:`search_colour`

.. _SHERPA/RoMEO: http://www.sherpa.ac.uk/romeo/
.. _web API: http://www.sherpa.ac.uk/romeo/api.html

The SHERPA/RoMEO API returns XML responses. This module wraps those in
:class:`~eulxml.xmlmap.XmlObject` instances:

 * :class:`Response`
 * :class:`Journal`
 * :class:`Publisher`
 * :class:`Mandate`
 * :class:`Copyright`

Note that we follow the SHERPA/RoMEO spelling of `colour` where it appears
in this module.

funder_info
~~~~~~~~~~~

Query functions in this module all take an optional `funder_info` argument.
If the argument is something other than ``'none'`` (the default), then
:class:`Publisher` objects in the response will include :class:`Mandate`
details for the funders matching the argument value. SHERPA/RoMEO accepts
the following values:

 * ``'none'``: Include no :class:`Mandate` details
 * ``'all'``: Include all :class:`Mandate` details for this
   :class:`Publisher`
 * a funder's full case-insensitive name from `JULIET`_: Include
   :class:`Mandate` details for the named funder
 * a funder's case-insensitive acronym from `JULIET`_: Include
   :class:`Mandate` details for the first funder matching the specified
   acronym
 * a funder's `JULIET`_ PID: Include :class:`Mandate` details for the
   identified funder
 * a `iso-3166 two-letter country code`: Include :class:`Mandate` details for
   funding by the identified country

.. _JULIET: http://www.sherpa.ac.uk/juliet/
.. _iso-3166 two-letter country code: http://www.iso.org/iso/country_codes/iso_3166_code_lists/country_names_and_code_elements.htm
'''

# SHERPA/RoMEO response details from:
#   http://www.sherpa.ac.uk/romeo/SHERPA%20RoMEO%20API%20V-2-4%202009-10-29.pdf
# at which also see Conditions of Use

from urllib.parse import urlencode
from urllib.request import urlopen
from django.conf import settings
from eulxml import xmlmap

__all__ = [
    'search_publisher_name', 'search_publisher_id', 'search_journal_title',
    'search_journal_followup', 'search_journal_issn', 'all_publishers',
    'search_colour',
    'Response', 'Journal', 'Publisher', 'Mandate', 'Copyright',
]

#API_BASE_URL = 'http://www.sherpa.ac.uk/romeo/api29.php'
API_BASE_URL = 'https://v2.sherpa.ac.uk/cgi/retrieve'
def call_api(**kwargs):
    if 'ak' not in kwargs:
        if hasattr(settings, 'ROMEO_API_KEY'):
            kwargs['api-key'] = settings.ROMEO_API_KEY
    query_args = urlencode(kwargs)
    url = '%s?%s' % (API_BASE_URL, query_args)
    print(url)
    response_file = None
    response = None
    try:
        response_file = urlopen(url)
        response = xmlmap.load_xmlobject_from_string(response_file.read(),
                        xmlclass=Response)
    finally:
        if response_file is not None:
            response_file.close()
    if response is not None:
        return response
    else:
        return Response() # dummy value to return when things have gone horribly wrong


def search_publisher_name(name, type=None, versions=None, funder_info=None):
    '''Search for a publisher by name.

        :param name: string of words in the name
        :param type: ``'all'`` to search for all tokens in any order;
                     ``'any'`` to search for one or more tokens in any
                     order; ``'exact'`` to search for the `name` as a
                     case-insensitive substring of the publisher name.
                     defaults to ``'all'``
        :param versions: ``'all'`` to include publisher policies for all
                         available versions. Without this, PDF policy
                         information will not be included
        :param funder_info: see module notes on `funder_info`
        :rtype: list of matching :class:`Publisher` objects
    '''
    # always returns empty journals
    kwargs = {'pub': name, 'item-type': 'publisher'}
    if type is not None:
        kwargs['qtype'] = type
    if versions is not None:
        kwargs['versions'] = versions
    if funder_info is not None:
        kwargs['showfunder'] = funder_info

    response = call_api(**kwargs)
    return response.publishers

def search_publisher_id(id, versions=None, funder_info=None):
    '''Search for a publisher by SHERPA/RoMEO id.

        :param id: a SHERPA/RoMEO identifier
        :param funder_info: see module notes on `funder_info`
        :rtype: matching :class:`Publisher`, or ``None``
    '''
    kwargs = {'id': id, 'item-type': 'publisher'}
    if versions is not None:
        kwargs['versions'] = versions
    if funder_info is not None:
        kwargs['showfunder'] = funder_info

    response = call_api(**kwargs)
    if response.outcome == 'publisherFound':
        return response.publishers[0]

def search_journal_title(name, type=None, versions=None, funder_info=None):
    '''Search for a journal by title.

        :param name: string
        :param type: ``'starts'`` to search for journals starting with
                     `name`; ``'contains'`` to search for journals
                     containing `name` as a substring`; ``'exact'`` for a
                     case-insensitive exact match with `name`. defaults to
                     ``'starts'``.
        :param versions: ``'all'`` to include publisher policies for all
                         available versions. Without this, PDF policy
                         information will not be included
        :param funder_info: see module notes on `funder_info`
        :rtype: list of :class:`Journal` objects
    '''
    # publishers empty for multiple journals; included for single match.
    # truncates to 50 titles (outcome=excessJournals on trunc).
    # if romeopub specified, it can be used for a journal followup search
    kwargs = {'jtitle': name, 'item-type': 'publication'}
    if type is not None:
        kwargs['qtype'] = type
    if versions is not None:
        kwargs['versions'] = versions
    if funder_info is not None:
        kwargs['showfunder'] = funder_info

    response = call_api(**kwargs)
    return response.journals

def search_journal_followup(name, publisher_zetoc, publisher_romeo,
                            issn=None, versions=None, funder_info=None):
    '''Search for a single journal by title and publisher name.

        :param name: string
        :param publisher_zetoc: publisher name in ZETOC database
        :param publisher_romeo: publisher name in RoMEO database
        :param issn: journal ISSN
        :param versions: ``'all'`` to include publisher policies for all
                         available versions. Without this, PDF policy
                         information will not be included
        :param funder_info: see module notes on `funder_info`
        :rtype: :class:`Journal` or ``None``
    '''
    kwargs = {
        'jtitle': name,
        'zetocpub': publisher_zetoc,
        'romeopub': publisher_romeo,
        'item-type': 'publication'
    }
    if issn is not None:
        kwargs['issn'] = issn
    if versions is not None:
        kwargs['versions'] = versions
    if funder_info is not None:
        kwargs['showfunder'] = funder_info

    response = call_api(**kwargs)
    if response.outcome == 'journalFound':
        return response.journals[0]

def search_journal_issn(issn, versions=None, funder_info=None):
    '''Search for a single journal by ISSN.

        :param issn: string
        :param funder_info: see module notes on `funder_info`
        :param versions: ``'all'`` to include publisher policies for all
                         available versions. Without this, PDF policy
                         information will not be included
        :rtype: :class:`Journal` or ``None``
    '''
    kwargs = {'issn': issn, 'item-type': 'publication'}
    if versions is not None:
        kwargs['versions'] = versions
    if funder_info is not None:
        kwargs['showfunder'] = funder_info

    response = call_api(**kwargs)
    if len(response.journals) == 1:
        return response.journals[0]

def all_publishers(versions=None, funder_info=None):
    '''Retrieve all publishers.

        :param versions: ``'all'`` to include publisher policies for all
                         available versions. Without this, PDF policy
                         information will not be included
        :param funder_info: see module notes on `funder_info`
        :rtype: list of :class:`Publisher` objects
    '''
    # in alphabetical name order. empty journals
    kwargs = {'all': 'yes', 'item-type': 'publisher'}
    if versions is not None:
        kwargs['versions'] = versions
    if funder_info is not None:
        kwargs['showfunder'] = funder_info

    response = call_api(**kwargs)
    return response.publishers

def search_colour(colour, versions=None, funder_info=None):
    '''Retrieve all publishers matching a SHERPA/RoMEO color.

        :param colour: ``'green'``, ``'blue'``, ``'yellow'``, or ``'white'``
        :param versions: ``'all'`` to include publisher policies for all
                         available versions. Without this, PDF policy
                         information will not be included
        :param funder_info: see module notes on `funder_info`
        :rtype: list of :class:`Publisher` objects
    '''
    # in alphabetical name order. empty journals
    kwargs = {'colour': colour}
    if versions is not None:
        kwargs['versions'] = versions
    if funder_info is not None:
        kwargs['showfunder'] = funder_info

    response = call_api(**kwargs)
    return response.publishers


class Mandate(xmlmap.XmlObject):
    '''A publisher's policy compliance with an open-access funding mandate
    from a research funder'''
    funder_name = xmlmap.StringField('funder/fundername')
    funder_acronym = xmlmap.StringField('funder/funderacronym')
    funder_juliet_url = xmlmap.StringField('funder/julieturl')
    publisher_complies = xmlmap.StringField('publishercomplies')
    # complies values: yes, no, unclear
    compliance_type = xmlmap.StringField('compliancetype')
    # compliance types in appendix c
    selected_titles = xmlmap.StringField('selectedtitles')
    # selected titles values: yes (or empty)

    def __repr__(self):
        return u'<%s: %s>' % (self.__class__.__name__, self.funder_name)

class Copyright(xmlmap.XmlObject):
    '''A link to a portion of a publisher's copyright policy
    documentation'''
    text = xmlmap.StringField('copyrightlinktext')
    url = xmlmap.StringField('copyrightlinkurl')

    def __repr__(self):
        return u'<%s: "%s" <%s>>' % (self.__class__.__name__, self.text, self.url)

class Publisher(xmlmap.XmlObject):
    '''A journal publisher'''
    id = xmlmap.StringField('@id')
    # numeric id for romeo records; 'DOAJ' for doaj records with no romeo data
    name = xmlmap.StringField('name')
    alias = xmlmap.StringField('alias')
    url = xmlmap.StringField('homeurl')
    # archiving values: can, cannot, restricted, unclear, unknown.
    # restrictions present only if restricted.
    preprint_archiving = xmlmap.StringField('preprints/prearchiving')
    preprint_restrictions = xmlmap.StringListField('preprints/prerestrictions/prerestriction')
    postprint_archiving = xmlmap.StringField('postprints/postarchiving')
    postprint_restrictions = xmlmap.StringListField('postprints/postrestrictions/postrestriction')
    pdf_archiving = xmlmap.StringField('pdfversion/pdfarchiving')
    pdf_restrictions = xmlmap.StringListField('pdfversion/pdfrestrictions/pdfrestriction')
    conditions = xmlmap.StringListField('conditions/condition')
    mandates = xmlmap.NodeListField('mandates/mandate', Mandate)
    paid_access_url = xmlmap.StringField('paidaccess/paidaccessurl')
    paid_access_name = xmlmap.StringField('paidaccess/paidaccessname')
    paid_access_notes = xmlmap.StringField('paidaccess/paidaccessnotes')
    copyright_links = xmlmap.NodeListField('copyrightlinks/copyrightlink', Copyright)
    romeo_colour = xmlmap.StringField('romeocolour')
    '''`Colour values <http://www.sherpa.ac.uk/romeoinfo.html#colours>`_
    used by RoMEO to describe archiving rights'''
    date_added = xmlmap.DateTimeField('dateadded', format='%Y-%m-%d %H:%M:%S')
    date_updated = xmlmap.DateTimeField('dateupdated', format='%Y-%m-%d %H:%M:%S')

    def __repr__(self):
        return u'<%s:%s %s>' % (self.__class__.__name__, self.id, self.name)

class Journal(xmlmap.XmlObject):
    '''A journal'''
    title = xmlmap.StringField('jtitle')
    issn = xmlmap.StringField('issn')
    publisher_zetoc = xmlmap.StringField('zetocpub')
    'publisher name in the Zetoc database'
    publisher_romeo = xmlmap.StringField('romeopub')
    'publisher name in the RoMEO database'

    _response_publisher = xmlmap.NodeField('/romeoapi/publishers/publisher', Publisher)
    '''a single publisher described in the query result that contains this
    journal. used internally.'''

    def __repr__(self):
        if self.issn:
            return u'<%s:%s %s>' % (self.__class__.__name__, self.issn, self.title)
        else:
            return u'<%s: %s>' % (self.__class__.__name__, self.title)

    def response_includes_publisher_details(self):
        '''Return ``True`` if the API response that contains this
        :class:`Journal` also contains its :class:`Publisher` details. If
        this method returns ``True`` then :meth:`publisher_details` will not
        require a new API request.'''
        return self._response_publisher is not None

    def publisher_details(self, versions=None, funder_info=None):
        '''The :class:`Publisher` of this journal. Returns the ``Publisher``
        included in the same response as this journal, if applicable;
        otherwise queries SHERPA/RoMEO for the publisher details.
        '''
        if self.response_includes_publisher_details():
            return self._response_publisher
        else:
            response = search_journal_followup(name=self.title,
                            publisher_zetoc=self.publisher_zetoc,
                            publisher_romeo=self.publisher_romeo,
                            issn=self.issn,
                            versions=versions,
                            funder_info=funder_info)
            if response.outcome == 'singleJournal':
                return response.publishers[0]

class Response(xmlmap.XmlObject):
    '''An XML response to a SHERPA/RoMEO query'''
    # this mapping ignores header/parameters
    num_hits = xmlmap.IntegerField('header/numhits')
    api_control = xmlmap.StringField('header/apicontrol')
    # api_control values: all, colour, followup, identifier, invalid,
    #                     journal, publisher
    outcome = xmlmap.StringField('header/outcome')
    # outcome values: excessJournals, failed, manyJournals, notFound,
    #                 publisherFound, singleJournal, uniqueZetoc
    message = xmlmap.StringField('header/message')
    journals = xmlmap.NodeListField('journals/journal', Journal)
    publishers = xmlmap.NodeListField('publishers/publisher', Publisher)

    def __repr__(self):
        if self.num_hits is None:
            return u'<%s: %s>' % (self.__class__.__name__, self.outcome)
        else:
            return u'<%s: %s (%d hits)>' % (self.__class__.__name__,
                    self.outcome, self.num_hits)
