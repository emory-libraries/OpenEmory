import logging
from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User

from eulxml.forms import XmlObjectForm, SubformField
from eulxml.xmlmap.dc import DublinCore
from eulxml.xmlmap import mods
from eullocal.django.emory_ldap.backends import EmoryLDAPBackend

from openemory.publication.models import ArticleMods, \
     Keyword, AuthorName, AuthorNote, FundingGroup, JournalMods

logger = logging.getLogger(__name__)

class UploadForm(forms.Form):
    'Single-file upload form.'
    pdf = forms.FileField(label='')

class BasicSearchForm(forms.Form):
    'single-input article text search form'
    keyword = forms.CharField()


class AffiliationTextInput(forms.TextInput):
    ''':class:`django.forms.TextInput` that renders read-only if its form's
    id field is set, editable otherwise.'''
    readonly_attrs = {
        'readonly': 'readonly',
        'class': 'readonly',
        'tabindex': '-1',
    }

    def render(self, name, value, attrs=None):
        super_render = super(AffiliationTextInput, self).render
        
        use_attrs = self.readonly_attrs.copy() if self.editable() else {}
        if attrs is not None:
            use_attrs.update(attrs)
        return super_render(name, value, use_attrs)

    def editable(self):
        '''Should this widget render as editable? Returns False if its
        form's id field (netid) is set, True otherwise.'''
        # relies on AuthorNameForm below setting this widget's form.
        return not self.form['id'].value()


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
            'affiliation': AffiliationTextInput,
        }

    def __init__(self, *args, **kwargs):
        super(AuthorNameForm, self).__init__(*args, **kwargs)
        # affiliation is optionally read-only depending on the value of the
        # id field. give that widget a reference to this form so that it can
        # make that determination.
        self.fields['affiliation'].widget.form = self
        
    def clean(self):
        # if id is set, affiliation should be Emory (no IDs for non-emory users)
        cleaned_data = self.cleaned_data
        id = cleaned_data.get('id')
        aff = cleaned_data.get('affiliation')
        if id and aff != 'Emory University':
            raise forms.ValidationError('ID is set but affiliation is not Emory University')
            
        return cleaned_data
    

class ArticleModsEditForm(XmlObjectForm):
    '''Form to edit the MODS descriptive metadata for an
    :class:`~openemory.publication.models.Article`.'''
    title_info = SubformField(formclass=ArticleModsTitleEditForm)
    authors = SubformField(formclass=AuthorNameForm)
    funders = SubformField(formclass=FundingGroupEditForm)
    journal = SubformField(formclass=JournalEditForm)
    abstract = SubformField(formclass=AbstractEditForm)
    keywords = SubformField(formclass=KeywordEditForm)
    author_notes = SubformField(formclass=AuthorNotesEditForm)
    class Meta:
        model = ArticleMods
        fields = ['title_info','authors', 'version', 'funders', 'journal',
                  'abstract', 'keywords', 'author_notes']

        

