# file openemory/publication/forms.py
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

import logging
import re
from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.forms.widgets import DateInput
from django.utils.datastructures import SortedDict
from django.utils.safestring import mark_safe
from django.contrib.localflavor.us.forms import USPhoneNumberField
# collections.OrderedDict not available until Python 2.7
import magic

from django.template.defaultfilters import slugify

from eulcommon.djangoextras.formfields import W3CDateWidget, DynamicChoiceField, \
     W3C_DATE_RE, W3CDateField
from eulxml.forms import XmlObjectForm, SubformField
from eulxml.xmlmap.dc import DublinCore
from eulxml.xmlmap import mods
from eullocal.django.emory_ldap.backends import EmoryLDAPBackend

from openemory.publication.models import PublicationMods, \
     Keyword, AuthorName, AuthorNote, FundingGroup, JournalMods, \
     FinalVersion, ResearchField, marc_language_codelist, ResearchFields, FeaturedArticle, License, \
    MODSCopyright, MODSAdminNote, SupplementalMaterial

from rdflib import Graph, URIRef

logger = logging.getLogger(__name__)

# Define Special options for embargo duration
NO_LIMIT = {"value":"Indefinite", "display":"Indefinite"}
UNKNOWN_LIMIT = {"value":"Not Known", "display":"Unknown"}

# NOTE: FileTypeValidator should be available in the next released
# version of eulcommon (0.17).  Switch this to
# eulcommon.djangoextras.validators.FileTypeValidator when it
# is available in a released version of eulcommon.
class FileTypeValidator(object):
    '''Validator for a :class:`django.forms.FileField` to check the
    mimetype of an uploaded file using :mod:`magic`.  Takes a list of
    mimetypes and optional message; raises a
    :class:`~django.core.exceptions.ValidationError` if the mimetype
    of the uploaded file is not in the list of allowed types.

    :param types: list of acceptable mimetypes
    :param message: optional error validation error message

    Example use::

        pdf = forms.FileField(label="PDF",
            validators=[FileTypeValidator(types=["application/pdf"],
                      message="Upload a valid PDF document.")])

    '''
    allowed_types = []

    def __init__(self, types, message=None):
        self.allowed_types = types
        if message is not None:
            self.message = message
        else:
            self.message = 'Upload a file in an allowed format: %s' % \
                           ', '.join(self.allowed_types)

    def __call__(self, data):
        """
        Validates that the input matches the specified mimetype.
        """
        # FIXME: check that data is an instance of
        # django.core.files.uploadedfile.UploadedFile ?

        m = magic.Magic(mime=True)
        # temporary file uploaded to disk (i.e., handled TemporaryFileUploadHandler)
        if hasattr(data, 'temporary_file_path'):
            mimetype = m.from_file(data.temporary_file_path())

        # in-memory file (i.e., handled by MemoryFileUploadHandler)
        else:
            if hasattr(data, 'read'):
                content = data.read()
            else:
                content = data['content']
            mimetype = m.from_buffer(content)

        type, separator, options = mimetype.partition(';')
        if type not in self.allowed_types:
            raise ValidationError(self.message)


class LocalW3CDateWidget(W3CDateWidget):
    '''Extend :class:`eulcommon.djangoextras.formfields.W3CDateWidget`
    to match display formatting provided by 352Media::

        <div class="formThird">
          <label for="publicationDay"> Day:</label>
          <input id="publicationDay" name="publicationDay" class="text" type="text" />
        </div>
        <div class="formThird">
          <label for="month">
          Month:</label>
          <input id="month" name="month" class="text" type="text" />
        </div>
        <div class="formThird">
          <label for="year">
          Year:*</label>
          <input id="year" name="year" class="text" type="text" />
        </div>

    '''
    # NOTE: this duplicates some logic from the eulcommon widget;
    # the eulcommon version should be modified to make it more extendable,
    # and this class should be refactored to take advantage of that.
    def render(self, name, value, attrs=None):
        '''Render the widget as HTML inputs for display on a form.

        :param name: form field base name
        :param value: date value
        :param attrs: - unused
        :returns: HTML text with three inputs for year/month/day,
           styled according to 352Media template layout
        '''

        # expects a value in format YYYY-MM-DD or YYYY-MM or YYYY (or empty/None)
        year, month, day = 'YYYY', 'MM', 'DD'
        help_text = {'year': year, 'month': month, 'day': day}
        if value:
            # use the regular expression to pull out year, month, and day values
            # if regular expression does not match, inputs will be empty
            match = W3C_DATE_RE.match(value)
            if match:
                date_parts = match.groupdict()
                year = date_parts['year']
                month = date_parts['month']
                day = date_parts['day']

        css_class = {'class': 'text'}
        output_template = '''<div class="formThird">
    <label for="%(id)s">%(label)s</label>
    %(input)s
</div>'''

        output = []
        attrs = css_class.copy()
        attrs['help_text'] = help_text['day']
        day_input = self.create_textinput(name, self.day_field, day, size=2,
                                          title='2-digit day',
                                          **attrs)
        output.append(output_template % {'id': self._field_id(name, self.day_field),
                                         'input': day_input,
                                         'label': 'Day'})
        attrs = css_class.copy()
        attrs['help_text'] = help_text['month']
        month_input = self.create_textinput(name, self.month_field, month, size=2,
                                          title='2-digit month',
                                          **attrs)
        output.append(output_template % {'id': self._field_id(name, self.month_field),
                                         'input': month_input,
                                         'label': 'Month'})
        attrs = css_class.copy()
        attrs['help_text'] = help_text['year']
        year_input = self.create_textinput(name, self.year_field, year, size=4,
            title='4-digit year', **attrs)

        output.append(output_template % {'id': self._field_id(name, self.year_field),
                                         'input': year_input,
                                         #not the best way to do this but
                                         # it will be very dificult to
                                         # seperat the * and the reset of the label
                                         # in this widget.
                                         'label': 'Year <span class="required">*</span>'})

        return mark_safe(u'\n'.join(output))

    def _field_id(self, name, field):
        # generate field id - duplicate logic from base class
        if 'id' in self.attrs:
            id_ = self.attrs['id']
        else:
            id_ = 'id_%s' % name
        return field % id_



# pdf validation error message - for upload pdf & author agreement
PDF_ERR_MSG = 'This document is not a valid PDF. Please upload a PDF, ' + \
              'or contact a system administrator for help.'

class UploadForm(forms.Form):
    'Single-file upload form with assent to deposit checkbox.'
    # LEGAL NOTE: assent is currently a required field. Legal counsel
    # recommends requiring assent to deposit before processing file upload.
    # The view that processes this form relies on the fact that failure to
    # assent will render the form invalid. Note that some legal language is
    # modified by AdminUploadForm, below.
    assent = forms.BooleanField(label='I accept these terms', required=True,
        help_text='Check to indicate your assent to the above policy. ' + \
                  'This is required to submit an article.',
        error_messages={'required': 'You must indicate assent to upload an article'},
        widget=forms.CheckboxInput(attrs={'class': 'outline'}))
    pdf = forms.FileField(label='Upload PDF',
         # customize default required message ('this field is required')
         error_messages={'required': 'A PDF file is required to submit an article.'},
         widget=forms.FileInput(attrs={'class': 'text'}),
         validators=[FileTypeValidator(types=['application/pdf'],
                                       message=PDF_ERR_MSG)])

class AdminUploadForm(UploadForm):
    '''Admin variant of :class:`UploadForm` with option to upload for
    another user'''
    # LEGAL NOTE: This form enables a second, alternate form of the upload
    # legal statement. This option is available only to admins.
    LEGAL_STATEMENT_CHOICES = (
            ('MEDIATED', 'I am depositing work on behalf of a faculty member.'),
            # ('AUTHOR', 'I am depositing my own work.'),
        )
    legal_statement = forms.ChoiceField(widget=forms.RadioSelect,
            choices=LEGAL_STATEMENT_CHOICES, required=True)


class BasicSearchForm(forms.Form):
    'single-input article text search form'
    keyword_help_text = 'Start searching here...'
    keyword = forms.CharField(initial=keyword_help_text,
        widget=forms.TextInput(attrs={'class': 'text searchInput', 'help_text':keyword_help_text}))
    # intial & widget change based on 352Media design; better solution?


class SearchWithinForm(BasicSearchForm):
    'single-input article text search form for searching within results'
    search_within_help_text='search within results...'
    within_keyword = forms.CharField(initial=search_within_help_text,
                              widget=forms.TextInput(attrs={'class': 'text', 'help_text': search_within_help_text}))
    # should be displayed as hidden to hold past filters for that search
    past_within_keyword = forms.CharField(required=False)
    # should be displayed as hidden to hold past filters for that search
    past_within_keyword = forms.CharField(required=False)

# read-only attributes; used by both read-only input variants below
READONLY_ATTRS = {
    'readonly': 'readonly',
    'class': 'readonly text',
    'tabindex': '-1',
}

class ReadOnlyTextInput(forms.TextInput):
    ''':class:`django.forms.TextInput` that renders as read-only. (In \
    addition to readonly, inputs will have CSS class ``readonly`` and a \
    tabindex of ``-1``.'''
    def __init__(self, attrs=None):
        use_attrs = READONLY_ATTRS.copy()
        if attrs is not None:
            use_attrs.update(attrs)
        super(ReadOnlyTextInput, self).__init__(attrs=use_attrs)


class OptionalReadOnlyTextInput(forms.TextInput):
    ''':class:`django.forms.TextInput` that renders read-only if the \
    form id field is set, editable otherwise.  Uses the same read-only \
    attributes as :class:`ReadOnlyTextInput`.'''

    def render(self, name, value, attrs=None):
        super_render = super(OptionalReadOnlyTextInput, self).render

        use_attrs = {'class': 'text'} if self.editable() else READONLY_ATTRS.copy()
        if attrs is not None:
            use_attrs.update(attrs)
        return super_render(name, value, use_attrs)

    def editable(self):
        '''Should this widget render as editable? Returns False if the \
        form id field is set, True otherwise.'''
        # relies on AuthorNameForm below setting this widget's form.
        return not self.form['id'].value()


## forms & subforms for editing article mods

class BaseXmlObjectForm(XmlObjectForm):
    # base xmlobjectform with CSS class declarations
    error_css_class = 'error'
    required_css_class = 'required'

class ArticleModsTitleEditForm(BaseXmlObjectForm):
    form_label = 'Title Information'
    subtitle = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'text'}))
    part_number = forms.CharField(required=False, label='Part #', widget=forms.TextInput(attrs={'class': 'text'}))
    part_name = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'text'}),
                                help_text='''If your article was published in more than one part, please enter the \
                                part number and name here.''')
    class Meta:
        model = mods.TitleInfo
        fields = ['title', 'subtitle', 'part_number', 'part_name']
        widgets = {
            'title':  forms.TextInput(attrs={'class': 'text'}),
        }

class PartDetailNumberEditForm(BaseXmlObjectForm):
    # part-detail form for number only - no label, not required
    number = forms.CharField(label='', required=False,
                          widget=forms.TextInput(attrs={'class': 'text'}))
    class Meta:
        model = mods.PartDetail
        fields = ['number']

class PartExtentEditForm(BaseXmlObjectForm):
    start = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'text'}))
    end = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'text'}))
    class Meta:
        model = mods.PartExtent
        fields = ['start', 'end']

class JournalEditForm(BaseXmlObjectForm):
    form_label = 'Publication Information'
    title = forms.CharField(label='Journal Title', widget=forms.TextInput(attrs={'class': 'text'}), required=False)
    issn = forms.CharField(label='ISSN', required=False)
    publisher = forms.CharField(label='Publisher', required=False)
    volume = SubformField(label='Volume #', formclass=PartDetailNumberEditForm,
                          widget=forms.TextInput(attrs={'class': 'text'}), required=False)
    number = SubformField(label='Issue #', formclass=PartDetailNumberEditForm,
                          widget=forms.TextInput(attrs={'class': 'text'}), required=False)
    pages = SubformField(formclass=PartExtentEditForm, label='Page Range', required=False)
    class Meta:
        model = JournalMods
        fields = ['title', 'issn', 'publisher', 'volume', 'number',
                  'pages']
        widgets = {
            'issn': forms.HiddenInput, # populated by autocomplete
        }



class BookEditForm(BaseXmlObjectForm):
    form_label = 'Book Information'
    book_title = forms.CharField(label='Book Title', widget=forms.TextInput(attrs={'class': 'text'}))
    class Meta:
        model = JournalMods
        fields = ['book_title']


class FundingGroupEditForm(BaseXmlObjectForm):
    form_label = 'Funding Group or Granting Agency'
    help_text = 'Begin typing and select from funders already in the system, \
                or continue typing to add a new one.'
    name = forms.CharField(label='', required=False, # suppress default label
                           widget=forms.TextInput(attrs={'class': 'text'}))
    class Meta:
        model = FundingGroup
        fields = ['name']
        extra = 0


class KeywordEditForm(BaseXmlObjectForm):
    help_text = 'Additional terms to describe the article. \
            Enter one word or phrase per input.  Begin typing and select from \
            suggestions to use keywords others have used, or continue typing to \
            add a new one.'
    topic = forms.CharField(label='', required=False, # suppress default label
                           widget=forms.TextInput(attrs={'class': 'text'}))
    class Meta:
        model = Keyword
        fields = ['topic']
        extra = 2

class AbstractEditForm(BaseXmlObjectForm):
    text = forms.CharField(label='',  # suppress default label
                           widget=forms.Textarea, required=False)
    class Meta:
        model = mods.Abstract
        fields = ['text']


class CopyrightEditForm(BaseXmlObjectForm):
    text = forms.CharField(label='Copyright Statement', widget=forms.TextInput(attrs={'class': 'text', 'style' : 'width:350px;'}),
                           required=False)
    class Meta:
        model = MODSCopyright
        fields = ['text']

class AdminNoteEditForm(BaseXmlObjectForm):
    text = forms.CharField(label='Admin Note', widget=forms.Textarea(attrs={'class': 'text'}),
                           required=False)
    class Meta:
        model = MODSAdminNote
        fields = ['text']

class AuthorNotesEditForm(BaseXmlObjectForm):
    text = forms.CharField(label='',  # suppress default label
                           widget=forms.Textarea, required=False)
    class Meta:
        model = AuthorNote
        fields = ['text']
        extra = 0

class SupplementalMaterialEditForm(BaseXmlObjectForm):
    form_label = 'SupplementalMaterials'
    url = forms.CharField(label='', required=False, # suppress default label
                           widget=forms.TextInput(attrs={'class': 'text'}))
    class Meta:
        model = SupplementalMaterial
        fields = ['url']
        extra = 0

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
            raise ValidationError(u'%s is not a recognized Emory user' % value)


class AuthorNameForm(BaseXmlObjectForm):
    help_text = 'Add authors in the order they should be listed.  \
                Use the suggestion field for Emory authors; click `add author` and  \
                enter name and affiliation for non-Emory authors. \
                You may drag and drop names to re-order them.'
    id = forms.CharField(label='Emory netid', required=False,
                         help_text='Supply Emory netid for Emory co-authors',
                         # validators=[validate_netid],
                         widget=forms.HiddenInput)
    family_name = forms.CharField(required=True, widget=OptionalReadOnlyTextInput,
                                  initial="last name")
    given_name = forms.CharField(required=True, widget=OptionalReadOnlyTextInput,
                                  initial="first name")
    affiliation = forms.CharField(required=False, widget=OptionalReadOnlyTextInput,
                                  initial="affiliation")
    class Meta:
        model = AuthorName
        fields = ['id', 'family_name', 'given_name', 'affiliation']
        extra = 0
        can_order = True

    def __init__(self, *args, **kwargs):
        super(AuthorNameForm, self).__init__(*args, **kwargs)
        # affiliation is optionally read-only depending on the value of the
        # id field. give that widget a reference to this form so that it can
        # make that determination.
        for fname in ['family_name', 'given_name', 'affiliation']:
            self.fields[fname].widget.form = self

    def clean(self):
        # if id is set, affiliation should be Emory (no IDs for non-emory users)
        cleaned_data = self.cleaned_data
        id = cleaned_data.get('id')
        aff = cleaned_data.get('affiliation')
        if id and aff != 'Emory University':
            raise forms.ValidationError('ID is set but affiliation is not Emory University')

        return cleaned_data


class FinalVersionForm(BaseXmlObjectForm):
    form_label = 'Final Published Version (URL)'
    url = forms.URLField(label="URL", required=False)
    doi = forms.RegexField(label="DOI", regex='^doi:10\.\d+/.*', required=False,
                           help_text='Enter DOI (if any) in doi:10.##/## format',
                           widget=forms.TextInput(attrs={'class': 'text'}))
    # NOTE: could potentially sanity-check DOIs by attempting to resolve them
    # as URLs (e.g., http://dx.doi.org/<doi>) - leaving that out for now
    # for simplicity and because we don't know how reliable it would be

    class Meta:
        model = FinalVersion
        fields = ['url', 'doi']

class OtherURLSForm(BaseXmlObjectForm):
    form_label = 'Other Versions (URL)'
    url = forms.URLField(label='' ,required=False,
                         widget=forms.TextInput(attrs={'class': 'text'}))
    class Meta:
        model = mods.Location
        fields = ['url']
        extra = 1

_language_codes = None
def language_codes():
    '''Generate and return a dictionary of language names and codes \
    from the MARC language Code List (as returned by \
    :meth:`~openemory.publication.models.marc_language_codelist`). \
    Key is language code, value is language name. \
    '''
    global _language_codes
    if _language_codes is None:
        lang_codelist = marc_language_codelist()
        # preserve the order of the languages in the document
        _language_codes = SortedDict((lang.code, lang.name)
                                      for lang in lang_codelist.languages)
    return _language_codes

def language_choices():
    '''List of language code and name tuples, for use as a \
    :class:`django.forms.ChoiceField` choice parameter'''
    codes = language_codes()
    # put english at the top of the list
    choices = [('eng', codes['eng'])]
    choices.extend((code, name) for code, name in codes.iteritems()
                   if code != 'eng')
    return choices

def license_choices():
    '''List of license for use as a \
    :class:`django.forms.ChoiceField` choice parameter'''

    options = [['', "no license"]]
    group_label = None
    group = []

    # Sort by version highest to lowest and then by title
    licenses = License.objects.all().order_by('-version', 'title')
    for l in licenses:
        # When the version changes add the current group to the options an start a new group
        if group_label!=None and group_label != "Version %s" % l.version:
            options.append([group_label, group])
            group = []
        # make each option and add it to the current group
        option = [l.url, l.label]
        group.append(option)
        group_label = "Version %s" % l.version

    # last group
    if group and group_label:
        options.append([group_label, group])

    return options


class SubjectForm(BaseXmlObjectForm):
    form_label = 'Subjects'
    class Meta:
        model = ResearchField
        fields = ['id', 'topic']
        widgets = {
            'id': forms.HiddenInput,
            'topic': ReadOnlyTextInput,
        }
        extra = 0

class ArticleModsEditForm(BaseXmlObjectForm):
    '''Form to edit the MODS descriptive metadata for an \
    :class:`~openemory.publication.models.Article`. \
    Takes optional :param: make_optional that makes all fields but Article Title optional \
    Takes optional :param: is_admin \
    Takes optional :param: nlm \
    '''
    title_info = SubformField(formclass=ArticleModsTitleEditForm)
    authors = SubformField(formclass=AuthorNameForm)
    funders = SubformField(formclass=FundingGroupEditForm)
    final_version = SubformField(formclass=FinalVersionForm)
    abstract = SubformField(formclass=AbstractEditForm)
    supplemental_materials = SubformField(formclass=SupplementalMaterialEditForm)
    copyright = SubformField(formclass=CopyrightEditForm)
    admin_note = SubformField(formclass=AdminNoteEditForm)
    keywords = SubformField(formclass=KeywordEditForm)
    author_notes = SubformField(formclass=AuthorNotesEditForm)
    #locations = SubformField(formclass=OtherURLSForm,
    #                         label=OtherURLSForm.form_label)
    language_code = DynamicChoiceField(language_choices, label='Language',
                                      help_text='Language of the article')
    subjects = SubformField(formclass=SubjectForm)

    # admin-only fields
    reviewed = forms.BooleanField(help_text='Select to indicate this article has been \
                                  reviewed; this will store a review event and remove \
                                  the article from the review queue.',
                                  required=False) # does not have to be checked
    withdraw = forms.BooleanField(help_text='Remove this article from the \
            public-facing parts of this site. It will still be visible to \
            admins and article authors.',
            required=False)
    withdraw_reason = forms.CharField(required=False, label='Reason',
            help_text='Reason for withdrawing this article')
    reinstate = forms.BooleanField(help_text='Return this withdrawn article \
            to the public-facing parts of this site.',
            required=False)
    reinstate_reason = forms.CharField(required=False, label='Reason',
            help_text='Reason for reinstating this article')

    publisher = forms.CharField(required=False, label='Publisher')

    publication_place = forms.CharField(required=False, label='Publication Place')

    _embargo_choices = [('','no embargo'),
                        ('6-months','6 months'),
                        ('12-months', '12 months'),
                        ('18-months', '18 months'),
                        ('24-months', '24 months'),
                        ('36-months', '36 months'),
                        ('48-months', '48 months'),
                        (slugify(UNKNOWN_LIMIT["value"]), UNKNOWN_LIMIT["display"]),
                        (slugify(NO_LIMIT["value"]), NO_LIMIT["display"])]

    embargo_duration = forms.ChoiceField(_embargo_choices,
        help_text='Restrict access to the PDF of your article for the selected time ' +
                  'after publication.', required=False)
    #author_agreement = forms.FileField(required=False,
    #                                   help_text="Upload a copy of the " +
    #                                   "article's author agreement.",
    #                                   widget=forms.FileInput(attrs={'class': 'text'}),
    #                                   validators=[FileTypeValidator(types=['application/pdf'],
    #                                                                 message=PDF_ERR_MSG)])
    publication_date = W3CDateField(widget=LocalW3CDateWidget,
        error_messages={'invalid':  u'Enter at least year (YYYY); ' +
                        u'enter two-digit month and day if known.',
                        'required': 'Publication year is required.'}
        )
    rights_research_date = forms.DateField(widget=DateInput(format='%Y-%m-%d', attrs={'class': 'text', 'style': 'width:150px'}),
                                           help_text= 'Format: yyyy-mm-dd', required=False, label='Rights Research Date')
    featured = forms.BooleanField(label='Featured', required=False,
    help_text='''Select to indicate this article has been featured;
    this will put this article in the list of possible articles that
    will appear on the home page.''')

    license = DynamicChoiceField(license_choices, label='Creative Commons License', required=False,
                                      help_text='Select appropriate license')

    class Meta:
        model = PublicationMods
        fields = ['title_info','authors', 'version', 'publication_date', 'subjects',
                  'funders', 'journal', 'final_version', 'abstract', 'keywords',
                  'author_notes', 'language_code', 'copyright', 'admin_note', 'rights_research_date',
                  'supplemental_materials','publication_place','publisher']

    '''
    :param: url: url of the license being referenced
    Looks up values for #permits terms on given license, retrieves the values
    from http://creativecommons.org/ns and constructs a description of the license.
    '''
    def _license_desc( self, url):
        permits_uri = URIRef("http://creativecommons.org/ns#permits")
        requires_uri = URIRef("http://creativecommons.org/ns#requires")
        prohibits_uri = URIRef("http://creativecommons.org/ns#prohibits")
        comment_uri = URIRef(u'http://www.w3.org/2000/01/rdf-schema#comment')
        ns_url = 'http://creativecommons.org/ns'


        license_graph = Graph()
        license_graph.parse(url)

        ns_graph = Graph()
        ns_graph.parse(ns_url)

        lines = []

        title = License.objects.get(url=url).title

        desc = 'This is an Open Access article distributed under the terms of the Creative Commons %s License \
        ( %s),' % (title, url)

        # get permits terms
        for t in license_graph.subject_objects(permits_uri):
            lines.append(ns_graph.value(subject=URIRef(t[1].replace('http:', 'https:')), predicate=comment_uri, object=None))

        if lines:
            lines = filter(None, lines)
            desc += ' which permits %s, provided the original work is properly cited.' % (', '.join(lines))

        # get requires terms
        lines = []
        for t in license_graph.subject_objects(requires_uri):
            lines.append(ns_graph.value(subject=URIRef(t[1].replace('http:', 'https:')), predicate=comment_uri, object=None))
        if lines:
            lines = filter(None, lines)
            desc += ' This license requires %s.' % (', '.join(lines))

        # get prohibits terms
        lines = []
        for t in license_graph.subject_objects(prohibits_uri):
            lines.append(ns_graph.value(subject=URIRef(t[1].replace('http:', 'https:')), predicate=comment_uri, object=None))
        if lines:
            lines = filter(None, lines)
            desc += ' This license prohibits %s.' % (', '.join(lines))

        #remove tabs, newlines and extra spaces
        desc = re.sub('\t+|\n+', ' ', desc)
        desc = re.sub(' +', ' ', desc)

        logger.debug('LICENSE DESC: %s' % desc)
        return desc

    def __init__(self, *args, **kwargs):
        #When set this marks the all fields EXCEPT for Title as optional
         make_optional = kwargs.pop('make_optional', False)
         is_admin = kwargs.pop('is_admin', False)
         is_nlm = kwargs.pop('is_nlm', False)
         genre = kwargs.pop('genre', False)
         self.pid = kwargs.pop('pid')
         
         ''':param: make_optional: when set this makes all the fields EXCEPT Article Title optional \
         Currently, only used in the case where the "Save" (vs Publish) button is used. \

         :param: pid: pid of the :class:`~openemory.publication.models.Article` being edited. Will be None \
         if user does not have the review perm or the article is not published. \
         '''
         super(ArticleModsEditForm, self).__init__(*args, **kwargs)

         if genre == "Article":
            print "got here"
            self.formsets['journal'] = SubformField(formclass=JournalEditForm)
         # set default language to english
         lang_code = 'language_code'
         self.fields['version'].required = False
         if lang_code not in self.initial or not self.initial[lang_code]:
             self.initial[lang_code] = 'eng'

         if  make_optional:
             for author_fs in self.formsets['authors']:
                 author_fs.fields['family_name'].required = False
                 author_fs.fields['given_name'].required = False

             self.fields['version'].required = False
             self.fields['publication_date'].required = False
             self.fields['language_code'].required = False
             self.subforms['journal'].fields['title'].required = False
             # self.subforms['journal'].fields['publisher'].required = False

         if is_admin and not is_nlm:
             self.fields['rights_research_date'].required = True

         embargo = 'embargo_duration'

         if embargo not in self.initial or not self.initial[embargo]:
             # if embargo is set in metadata, use that as initial value

             if self.instance.embargo:
                 self.initial[embargo] = slugify(self.instance.embargo)

             elif "_embargo" in self.initial and self.initial["_embargo"]:
                 self.initial[embargo] = self.initial["_embargo"]
             # otherwise, fall through to default choice (no embargo)

         license = 'license'
         if self.instance.license:
             self.initial[license] = self.instance.license.link

    def clean(self):
        cleaned_data = super(ArticleModsEditForm, self).clean()

        withdraw = self.cleaned_data.get('withdraw', False)
        withdraw_reason = self.cleaned_data.get('withdraw_reason', '')
        if self.cleaned_data.get('withdraw', False) and not withdraw_reason:
            message = "Withdrawal reason is required."
            self._errors['withdraw_reason'] = self.error_class([message])

        reinstate = self.cleaned_data.get('reinstate', False)
        reinstate_reason = self.cleaned_data.get('reinstate_reason', '')
        if self.cleaned_data.get('reinstate', False) and not reinstate_reason:
            message = "Reinstate reason is required."
            self._errors['reinstate_reason'] = self.error_class([message])

        return cleaned_data

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

            embargo = self.cleaned_data.get('embargo_duration', None)

            # if not set or no embargo selected, clear out any previous value
            if embargo is None or not embargo:
                del self.instance.embargo
            else:
                self.instance.embargo = embargo

            if self.pid: # only do this if pid is set which means that the user has the correct perms
                # set / remove featured article
                featured = self.cleaned_data.get('featured')
                try:
                    featured_article = FeaturedArticle.objects.get(pid=self.pid)
                except FeaturedArticle.DoesNotExist:
                    featured_article = FeaturedArticle(pid=self.pid)
                if featured: # box is checked on form
                    featured_article.save()
                elif featured is not None and featured_article.id: #have to check it exists before you delete
                    featured_article.delete()

            license_url = self.cleaned_data.get('license')
            if license_url:
                self.instance.create_license()
                self.instance.license.link = license_url
                self.instance.license.text = self._license_desc(license_url)
            else:
                self.instance.license = None

        # return object instance
        return self.instance

class OpenAccessProposalForm(forms.Form):
    status_choices = (
        ('faculty', 'Faculty'),
        ('post-doc', 'Post-Doc'),
        ('graduate-student', 'Current Graduate Student'),
        ('undergraduate-student', 'Current Undergraduate Student'),
    )

    funding_status_choices =(
        ('Not yet submitted', 'Not yet submitted'),
        ('Submitted but not yet accepted', 'Submitted but not yet accepted'),
        ('Accepted but not yet published', 'Accepted but not yet published'),
        ('Published', 'Published')
    )

    seeking_choices = (
        ('Yes', 'Yes'),
        ('No', 'No'),
    )

    funding_status = forms.ChoiceField(label='Funding Status', widget=forms.Select(attrs={'class': 'text'}), choices=funding_status_choices, required=True)
    author_first_name = forms.CharField(label='First Name', widget=forms.TextInput(attrs={'class': 'text'}), required=True)
    author_last_name = forms.CharField(label='Last Name', widget=forms.TextInput(attrs={'class': 'text'}), required=True)
    co_authors = forms.CharField(label='Co-Authors', widget=forms.TextInput(attrs={'class': 'text'}), required=True, help_text="If sole author enter none")
    department = forms.CharField(label='Department', widget=forms.TextInput(attrs={'class': 'text'}), required=True)
    school_div = forms.CharField(label='School or Division', widget=forms.TextInput(attrs={'class': 'text'}), required=True)
    email = forms.EmailField(label='Email', widget=forms.TextInput(attrs={'class': 'text'}), required=True)
    phone = USPhoneNumberField(label='Phone', widget=forms.TextInput(attrs={'class': 'text'}), required=True)
    #status = forms.CharField(label='Status', widget=forms.TextInput(attrs={'class': 'text'}), required=True)
    status = forms.ChoiceField(label='Status', choices=status_choices)
    journal_book_title = forms.CharField(label='Journal or Book Title', widget=forms.TextInput(attrs={'class': 'text'}), required=True)
    publisher = forms.CharField(label='Publisher', widget=forms.TextInput(attrs={'class': 'text'}), required=True)
    article_title = forms.CharField(label='Article Title (if book, enter N/A)', widget=forms.TextInput(attrs={'class': 'text'}), required=True)
    expected_pub_date = forms.DateField(label='Expected Pub Date', widget=forms.DateInput(attrs={'class':'text'}), required=True, help_text='YYYY-MM-DD or MM/DD/YYYY')
    pub_fees = forms.DecimalField(label='Publication Fees', widget=forms.TextInput(attrs={'class': 'text'}), decimal_places=2, required=True)
    seeking_funds = forms.CharField(required=True, widget=forms.RadioSelect(choices=seeking_choices),  label="Are you seeking funds for data archiving?")
    data_repository = forms.CharField(label='Data Repository', widget=forms.TextInput(attrs={'class': 'text'}), required=False, help_text="Required when answering Yes")
    archiving_fees = forms.DecimalField(label='Archiving Fees', widget=forms.TextInput(attrs={'class': 'text'}), decimal_places=2, required=False, help_text="Required when answering Yes")
