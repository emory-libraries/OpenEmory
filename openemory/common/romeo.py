# SHERPA/RoMEO API access. See:
#   http://www.sherpa.ac.uk/romeo/api.html
# response details from:
#   http://www.sherpa.ac.uk/romeo/SHERPA%20RoMEO%20API%20V-2-4%202009-10-29.pdf
# at which also see Conditions of Use

from urllib import urlencode
from urllib2 import urlopen
from django.conf import settings
from eulxml import xmlmap

# Many search calls may take a funder_info argument. it may take the
# following values:
#  none: no funder info (the default)
#  all: show all info on funder mandate compliance
#  funder's full case-insensitive name from juliet
#    http://www.sherpa.ac.uk/juliet/
#  funder's case-insensitive acronym from juliet (not unique; api returns
#    first match)
#  funder's juliet pid
#  two-letter iso-3166 country code (eg, 'AU')

API_BASE_URL = 'http://www.sherpa.ac.uk/romeo/api29.php'
def call_api(**kwargs):
    if 'ak' not in kwargs:
        if hasattr(settings, 'ROMEO_API_KEY'):
            kwargs['ak'] = settings.ROMEO_API_KEY
    query_args = urlencode(kwargs)
    url = '%s?%s' % (API_BASE_URL, query_args)
    response_file = urlopen(url)
    try:
        response = xmlmap.load_xmlobject_from_string(response_file.read(),
                        xmlclass=Response)
    finally:
        response_file.close()
    return response

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
    kwargs = {'pub': name}
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
    kwargs = {'id': id}
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
    kwargs = {'jtitle': name}
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
        :rtype: :class:`Response` with a single journal and single publisher
                if a match is found
    '''
    kwargs = {
        'jtitle': name,
        'zetocpub': publisher_zetoc,
        'romeopub': publisher_romeo,
    }
    if issn is not None:
        kwargs['issn'] = issn
    if versions is not None:
        kwargs['versions'] = versions
    if funder_info is not None:
        kwargs['showfunder'] = funder_info

    return call_api(**kwargs)

def search_journal_issn(issn, versions=None, funder_info=None):
    '''Search for a single journal by ISSN.

        :param issn: string
        :param funder_info: see module notes on `funder_info`
        :param versions: ``'all'`` to include publisher policies for all
                         available versions. Without this, PDF policy
                         information will not be included
        :rtype: :class:`Journal` or ``None``
    '''
    kwargs = {'issn': issn}
    if versions is not None:
        kwargs['versions'] = versions
    if funder_info is not None:
        kwargs['showfunder'] = funder_info

    response = call_api(**kwargs)
    if response.outcome == 'journalFound':
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
    kwargs = {'all': 'yes'}
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
    text = xmlmap.StringField('copyrightlinktext')
    url = xmlmap.StringField('copyrightlinkurl')

    def __repr__(self):
        return u'<%s: "%s" <%s>>' % (self.__class__.__name__, self.text, self.url)

class Publisher(xmlmap.XmlObject):
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
    # colour values: green, blue, yellow, white, gray. see
    #    http://www.sherpa.ac.uk/romeoinfo.html#colours
    date_added = xmlmap.DateTimeField('dateadded', format='%Y-%m-%d %H:%M:%S')
    date_updated = xmlmap.DateTimeField('dateadded', format='%Y-%m-%d %H:%M:%S')

    def __repr__(self):
        return u'<%s:%s %s>' % (self.__class__.__name__, self.id, self.name)

class Journal(xmlmap.XmlObject):
    title = xmlmap.StringField('jtitle')
    issn = xmlmap.StringField('issn')
    publisher_zetoc = xmlmap.StringField('zetocpub')
    publisher_romeo = xmlmap.StringField('romeopub')

    _response_outcome = xmlmap.StringField('/romeoapi/header/outcome')
    _response_publisher = xmlmap.NodeField('/romeoapi/publishers/publisher', Publisher)

    def __repr__(self):
        if self.issn:
            return u'<%s:%s %s>' % (self.__class__.__name__, self.issn, self.title)
        else:
            return u'<%s: %s>' % (self.__class__.__name__, self.title)

    def publisher_details(self, versions=None, funder_info=None):
        if self._response_outcome in ('singleJournal', 'publisherFound'):
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
