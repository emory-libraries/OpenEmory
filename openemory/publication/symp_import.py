from eulxml import xmlmap
from django.conf import settings


# Symplectic Import Models
class SympBase(xmlmap.XmlObject):
    '''
    Base class for Symplectic-Elements xml
    '''

    api_ns = 'http://www.symplectic.co.uk/publications/api'
    atom_ns = 'http://www.w3.org/2005/Atom'
    ROOT_NAMESPACES = {'api': api_ns, 'atom': atom_ns}
    ROOT_NS = api_ns
    XSD_SCHEMA = settings.BASE_DIR + '/publication/symp-api46.xsd'


class SympEntry(SympBase):
    '''Minimal wrapper for Symplectic-Elements article'''

    ROOT_NS = 'http://www.w3.org/2005/Atom'
    ROOT_NAME = 'entry'


    source = xmlmap.StringField("(api:object/api:records/api:record/@source-name)[1]")
    '''first symplectic source of publication'''

    source_id = xmlmap.StringField("(api:object/api:records/api:record/@id-at-source)[1]")
    '''id in first symplectic source'''

    title = xmlmap.StringField('atom:title')
    '''title of article'''


class SympOEImportPublication(SympBase):
    '''Minimal wrapper for Symplectic-Elements articles being imported into OE'''

    ROOT_NS = 'http://www.w3.org/2005/Atom'
    ROOT_NAME = 'feed'

    entries = xmlmap.NodeListField('atom:entry', SympEntry)
    '''List of Articles'''

    #TODO Remaining feilds that needto be found
    # Authors (FN, LN, AFF, netids for owners)
    # Article Version


# Import into Symplectic-Elements

class SympPerson(SympBase):
    '''Person Info'''

    ROOT_NAME = 'person'

    last_name = xmlmap.StringField('api:last-name')
    '''Last name of person'''

    initials = xmlmap.StringField('api:initials')
    '''Initials of person'''

class SympDate(SympBase):
    '''Date Info'''

    ROOT_NAME = 'date'

    day = xmlmap.StringField('api:day')
    '''Day portion of date'''

    month = xmlmap.StringField('api:month')
    '''Month portion of date'''

    year = xmlmap.StringField('api:year')
    '''Year portion of date'''



class SympWarning(SympBase):
    '''Warning returned from publication creation'''

    ROOT_NAME = 'warning'

    message = xmlmap.StringField("text()")
    '''Warning message'''


class OESympImportPublication(SympBase):
    '''Minimal wrapper for Symplectic-Elements articles being imported from OE'''

    ROOT_NAME = 'import-record'

    types = xmlmap.StringListField("api:native/api:field[@name='types']/api:items/api:item")
    '''Subtype of publication (defaults to Article)'''

    type_id = xmlmap.StringField("@type-id")
    '''Type Id of Article (defaults to 5)'''

    title = xmlmap.StringField("api:native/api:field[@name='title']/api:text")
    '''Title of Article'''

    language = xmlmap.StringField("api:native/api:field[@name='language']/api:text")
    '''Language of Article'''

    abstract = xmlmap.StringField("api:native/api:field[@name='abstract']/api:text")
    '''Abstract of Article'''

    volume = xmlmap.StringField("api:native/api:field[@name='volume']/api:text")
    '''Volume of Article'''

    issue = xmlmap.StringField("api:native/api:field[@name='issue']/api:text")
    '''Volume of Article'''

    publisher = xmlmap.StringField("api:native/api:field[@name='publisher']/api:text")
    '''Publisher of Article'''

    publisher = xmlmap.StringField("api:native/api:field[@name='publisher']/api:text")
    '''Publisher of Article'''

    publication_date = xmlmap.NodeField("api:native/api:field[@name='publication-date']/api:date", SympDate)
    '''Date of publication of Article'''

    authors = xmlmap.NodeListField("api:native/api:field[@name='authors']/api:people/api:person", SympPerson)
    '''Authors associated with Article'''

    doi = xmlmap.StringField("api:native/api:field[@name='doi']/api:text")
    '''DOI of Article'''

    keywords = xmlmap.StringListField("api:native/api:field[@name='keywords']/api:keywords/api:keyword")
    '''Keywords of Article'''

    journal = xmlmap.StringField("api:native/api:field[@name='journal']/api:text")
    '''Journal Name in which the Article appears'''

    notes = xmlmap.StringField("api:native/api:field[@name='notes']/api:text")
    '''Author Notes on the Article'''

    pmcid = xmlmap.StringField("api:native/api:field[@name='external-identifiers']/api:identifiers/api:identifier[@scheme='pmc']")
    '''PMCID Article appears'''


    warnings = xmlmap.NodeListField('//api:warning', SympWarning)
    '''Warning returned after publication creation'''

    entries = xmlmap.NodeListField('//atom:entry', SympEntry)
    '''entries returned from query'''


    def __init__(self, *args, **kwargs):
        super(OESympImportPublication, self).__init__(*args, **kwargs)

        self.type_id = 5

        self.types = ["Article","Book","Chapter","Conference","Poster","Dataset"]

    def is_empty(self):
        """Returns True if all fields are empty, and no attributes
        other than **type_id** . False if any fields
        are not empty."""

        # ignore these fields when checking if a related item is empty
        ignore = ['type_id', 'types']  # type attributes

        for name in self._fields.iterkeys():
            if name in ignore:
                continue
            f = getattr(self, name)
            # if this is an XmlObject or NodeListField with an
            # is_empty method, rely on that
            if hasattr(f, 'is_empty'):
                if not f.is_empty():
                    return False
            # if this is a list or value field (int, string), check if empty
            elif not (f is None or f == '' or f == []):
                return False

        # no non-empty non-ignored fields were found - return True
        return True


class SympRelation(SympBase):
    '''Minimal wrapper for Symplectic-Elements relation being imported from OE'''

    ROOT_NAME = 'import-relationship'


    # Types of relations
    PUB_AUTHOR = 'publication-user-authorship'


    from_object = xmlmap.StringField("api:from-object")

    to_object = xmlmap.StringField("api:to-object")

    type_name = xmlmap.StringField("api:type-name")
    '''Relation type'''