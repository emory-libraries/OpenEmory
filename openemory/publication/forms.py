import logging
from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User

from eulcommon.djangoextras.formfields import W3CDateWidget
from eulxml.forms import XmlObjectForm, SubformField
from eulxml.xmlmap.dc import DublinCore
from eulxml.xmlmap import mods
from eullocal.django.emory_ldap.backends import EmoryLDAPBackend

from openemory.publication.models import ArticleMods, \
     Keyword, AuthorName, AuthorNote, FundingGroup, JournalMods, \
     FinalVersion

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
    class Meta:
        model = ArticleMods
        fields = ['title_info','authors', 'version', 'publication_date',
                  'funders', 'journal', 'final_version', 'abstract', 'keywords',
                  'author_notes', 'locations']
        widgets = {
            'publication_date': W3CDateWidget,
        }

        

