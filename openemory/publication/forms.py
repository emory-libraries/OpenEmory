import logging
from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.utils.datastructures import SortedDict
# collections.OrderedDict not available until Python 2.7

from eulcommon.djangoextras.formfields import W3CDateWidget, DynamicChoiceField
from eulxml.forms import XmlObjectForm, SubformField
from eulxml.xmlmap.dc import DublinCore
from eulxml.xmlmap import mods
from eullocal.django.emory_ldap.backends import EmoryLDAPBackend

from openemory.publication.models import ArticleMods, \
     Keyword, AuthorName, AuthorNote, FundingGroup, JournalMods, \
     FinalVersion, marc_language_codelist

logger = logging.getLogger(__name__)

class UploadForm(forms.Form):
    'Single-file upload form.'
    pdf = forms.FileField(label='')

class BasicSearchForm(forms.Form):
    'single-input article text search form'
    keyword = forms.CharField()


class ReadonlyTextInput(forms.TextInput):
    'Read-only variation on :class:`django.forms.TextInput`'
    readonly_attrs = {
        'readonly': 'readonly',
        'class': 'readonly',
        'tabindex': '-1',
    }
    def __init__(self, attrs=None):
        if attrs is not None:
            self.readonly_attrs.update(attrs)
        super(ReadonlyTextInput, self).__init__(attrs=self.readonly_attrs)


## forms & subforms for editing article mods

class ArticleModsTitleEditForm(XmlObjectForm):
    form_label = 'Title Information'
    subtitle = forms.CharField(required=False)
    part_number = forms.CharField(required=False)
    part_name = forms.CharField(required=False)
    class Meta:
        model = mods.TitleInfo
        fields = ['title', 'subtitle', 'part_number', 'part_name']

class PartDetailNumberEditForm(XmlObjectForm):
    # part-detail form for number only - no label, not required
    number = forms.CharField(label='', required=False)
    class Meta:
        model = mods.PartDetail
        fields = ['number']

class PartExtentEditForm(XmlObjectForm):
    start = forms.CharField(required=False)
    end = forms.CharField(required=False)
    class Meta:
        model = mods.PartExtent
        fields = ['start', 'end']


class JournalEditForm(XmlObjectForm):
    form_label = 'Journal Information'
    volume = SubformField(formclass=PartDetailNumberEditForm)
    number = SubformField(formclass=PartDetailNumberEditForm)
    pages = SubformField(formclass=PartExtentEditForm)
    class Meta:
        model = JournalMods
        fields = ['title', 'publisher', 'volume', 'number',
                  'pages']

class FundingGroupEditForm(XmlObjectForm):
    form_label = 'Funding Group or Granting Agency'
    name = forms.CharField(label='', required=False) # suppress default label
    class Meta:
        model = FundingGroup
        fields = ['name']


class KeywordEditForm(XmlObjectForm):
    topic = forms.CharField(label='', required=False) # suppress default label
    class Meta:
        model = Keyword
        fields = ['topic']

class AbstractEditForm(XmlObjectForm):
    text = forms.CharField(label='',  # suppress default label
                           widget=forms.Textarea, required=False)
    class Meta:
        model = mods.Abstract
        fields = ['text']

class AuthorNotesEditForm(XmlObjectForm):
    text = forms.CharField(label='',  # suppress default label
                           widget=forms.Textarea, required=False)
    class Meta:
        model = AuthorNote
        fields = ['text']

def validate_netid(value):
    '''Validate a netid field by checking if the specified netid is
    either a username in the local database or can be found in LDAP.'''
    if not User.objects.filter(username=value).exists():
        ldap = EmoryLDAPBackend()
        # log ldap requests; using repr so it is evident when ldap is a Mock
        logger.debug('Looking up user in LDAP by netid \'%s\' (using %r)' \
                     % (value, ldap))
        user_dn, user = ldap.find_user(value)
        if not user:
            raise ValidationError(u'%s is not a recognized Emory netid' % value)
    

class AuthorNameForm(XmlObjectForm):
    id = forms.CharField(label='Emory netid', required=False,
                         help_text='Supply Emory netid for Emory co-authors',
                         validators=[validate_netid],
                         widget=forms.TextInput(attrs={'class':'netid-lookup'}))
    class Meta:
        model = AuthorName
        fields = ['id', 'family_name', 'given_name', 'affiliation']
        widgets = {
            # making affiliation read-only for now
            # (will need to be toggle-able once we add non-emory authors)
            'affiliation': ReadonlyTextInput,
        }
        
    def clean(self):
        # if id is set, affiliation should be Emory (no IDs for non-emory users)
        cleaned_data = self.cleaned_data
        id = cleaned_data.get('id')
        aff = cleaned_data.get('affiliation')
        if id and aff != 'Emory University':
            raise forms.ValidationError('ID is set but affiliation is not Emory University')
            
        return cleaned_data
    

class FinalVersionForm(XmlObjectForm):
    form_label = 'Final Published Version'
    url = forms.URLField(label="URL", verify_exists=True, required=False)
    doi = forms.RegexField(label="DOI", regex='^doi:10\.\d+/.*', required=False,
                           help_text='Enter DOI (if any) in doi:10.##/## format')
    # NOTE: could potentially sanity-check DOIs by attempting to resolve them 
    # as URLs (e.g., http://dx.doi.org/<doi>) - leaving that out for now
    # for simplicity and because we don't know how reliable it would be
    
    class Meta:
        model = FinalVersion
        fields = ['url', 'doi']

class OtherURLSForm(XmlObjectForm):
    form_label = 'URLs for other versions'
    url = forms.URLField(label="URL", verify_exists=True, required=False)
    class Meta:
        model = mods.Location
        fields = ['url']

_language_codes = None
def language_codes():
    '''Generate and return a dictionary of language names and codes
    from the MARC language Code List (as returned by
    :meth:`~openemory.publication.models.marc_language_codelist`).
    Key is language code, value is language name.
    '''
    global _language_codes
    if _language_codes is None:
        lang_codelist = marc_language_codelist()
        # preserve the order of the languages in the document
        _language_codes = SortedDict((lang.code, lang.name)
                                      for lang in lang_codelist.languages)
    return _language_codes

def language_choices():
    '''List of language code and name tuples, for use as a
    :class:`django.forms.ChoiceField` choice parameter'''
    codes = language_codes()
    # put english at the top of the list
    choices = [('eng', codes['eng'])]
    choices.extend((code, name) for code, name in codes.iteritems()
                   if code != 'eng')
    return choices


class ArticleModsEditForm(XmlObjectForm):
    '''Form to edit the MODS descriptive metadata for an
    :class:`~openemory.publication.models.Article`.'''
    title_info = SubformField(formclass=ArticleModsTitleEditForm)
    authors = SubformField(formclass=AuthorNameForm)
    funders = SubformField(formclass=FundingGroupEditForm)
    journal = SubformField(formclass=JournalEditForm)
    final_version = SubformField(formclass=FinalVersionForm)
    abstract = SubformField(formclass=AbstractEditForm)
    keywords = SubformField(formclass=KeywordEditForm)
    author_notes = SubformField(formclass=AuthorNotesEditForm)
    locations = SubformField(formclass=OtherURLSForm,
                             label=OtherURLSForm.form_label)
    language_code = DynamicChoiceField(language_choices, label='Language',
                                      help_text='Language of the article')
    class Meta:
        model = ArticleMods
        fields = ['title_info','authors', 'version', 'publication_date',
                  'funders', 'journal', 'final_version', 'abstract', 'keywords',
                  'author_notes', 'locations', 'language_code']
        widgets = {
            'publication_date': W3CDateWidget,
        }

    def __init__(self, *args, **kwargs):       
         super(ArticleModsEditForm, self).__init__(*args, **kwargs)
         # set default language to english
         lang_code = 'language_code'
         if lang_code not in self.initial or not self.initial[lang_code]:
             self.initial[lang_code] = 'eng'

    def update_instance(self):
        # override default update to handle extra fields
        super(ArticleModsEditForm, self).update_instance()
        
        # cleaned data only available when the form is actually valid
        if hasattr(self, 'cleaned_data'):
            # set or clear language text value based on language code
            lang_code = self.cleaned_data.get('language_code', None)
            if lang_code is None:
                # if language code is blank, clear out language text 
                self.instance.language = None
            else:
                # otherwise, set text value based on language code
                self.instance.language = language_codes()[lang_code]
                
        # return object instance
        return self.instance
