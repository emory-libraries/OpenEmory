from cStringIO import StringIO
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from eullocal.django.emory_ldap.models import AbstractEmoryLDAPUserProfile
from taggit.managers import TaggableManager
from taggit.models import TaggedItem
import logging
from PIL import Image
from south.modelsinspector import add_introspection_rules

from openemory.util import solr_interface
from openemory.accounts.fields import YesNoBooleanField
from openemory.publication.models import Article
from openemory.publication.views import ARTICLE_VIEW_FIELDS

logger = logging.getLogger(__name__)

add_introspection_rules([], ['^openemory\.accounts\.fields\.YesNoBooleanField'])

class UserProfile(AbstractEmoryLDAPUserProfile):
    user = models.OneToOneField(User)
    research_interests = TaggableManager(verbose_name='Research Interests',
        help_text='Comma-separated list of public research interests',
        blank=True)
    show_suppressed = models.BooleanField(default=False,
        help_text='Show information even if directory or internet suppressed')
    nonfaculty_profile = models.BooleanField(default=False,
        help_text='User is allowed to have a profile even if they are non-faculty')
    photo = models.ImageField(upload_to='profile-photos/%Y/%m/',
                              blank=True, default='')
    	# image field has height_field and width_field options; do we need those?
    biography = models.TextField(help_text='Biographical paragraph for public profile',
        blank=True, default='')

    class Meta:
        ordering = ['user__username']


    def _find_articles(self):
        '''Query Solr to find articles by this author.  Returns a solr
        query filtered by owner and content model, and fields limited
        to the standard view fields.

        Internal method with common functionality for
        :meth:`recent_articles` and :meth:`unpublished_articles`.

        '''
        solr = solr_interface()
        return solr.query(owner=self.user.username) \
                        .filter(content_model=Article.ARTICLE_CONTENT_MODEL) \
                        .field_limit(ARTICLE_VIEW_FIELDS) \

    def recent_articles(self, limit=3):
        '''Query Solr to find recent articles by this author.

        :param limit: number of articles to return. (defaults to 3)
        '''
        solrquery = self._find_articles()
        solrquery = solrquery.filter(state='A') \
                        .sort_by('-last_modified')
        return solrquery.paginate(rows=limit).execute()

    def unpublished_articles(self):
        '''Query Solr to find unpublished articles by this author.
        '''
        solrquery = self._find_articles()
        solrquery = solrquery.filter(state='I') \
                        .sort_by('-last_modified')
        return solrquery.execute()

    def esd_data(self):
        '''Find the :class:`EsdPerson` corresponding to this profile.
        '''
        # TODO: It would be nice to have a ForeignKey field for this, but
        # the capitalization looks like it would require subclassing
        # ForeignKey, which looks a little insane.
        return EsdPerson.objects.get(netid=self.user.username.upper())

    @property
    def suppress_esd_data(self):
        '''Boolean property to indicate whether ESD data can be shown
        (e.g., on a profile page), based on
        :attr:`EsdPerson.internet_suppressed` and
        :attr:`EsdPerson.directory_suppressed` flag and on the profile
        override flag, :attr:`UserProfile.show_suppressed`.

        If True, ESD data should be suppressed. If False, ESD data can
        be displayed.
        '''
        esd_data = self.esd_data()
        return (esd_data.internet_suppressed or esd_data.directory_suppressed) \
               and not self.show_suppressed


    def has_profile_page(self):
        '''Return ``True`` if the user should have a public-facing web
        profile on the site, ``False`` if not.

        Currently only faculty or users with nonfaculty_profile flag = True have profiles.
        '''

        esd_data = None
        try:
            esd_data = self.esd_data()
        except EsdPerson.DoesNotExist:
            pass

        # user is faculty or has nonfaculty_profile flag set
        return (esd_data and esd_data.has_profile_page()) or \
            self.nonfaculty_profile

    PHOTO_MAX_WIDTH = 300

    def resize_photo(self):
        '''Resize the :attr:`photo` associated with this profile (if
        any) to :attr:`PHOTO_MAX_WIDTH`, preserving aspect ratio.  If
        the image width is already smaller than
        :attr:`PHOTO_MAX_WIDTH`, no changes are made.
        '''
        if self.photo:
            # if the photo is smaller than our maximum size, don't do anything
            if self.photo.width <= self.PHOTO_MAX_WIDTH:
                logger.debug('Photo size is %dx%d; not resizing to max width %d' % \
                             (self.photo.width, self.photo.height,
                              self.PHOTO_MAX_WIDTH))
                return

            # calculate the scale from current photo width to max width
            scale = float(self.PHOTO_MAX_WIDTH) / float(self.photo.width)
            new_height = int(self.photo.height*scale)
            logger.debug('Scaling photo from %dx%d to %dx%d (%.02f)' % \
                             (self.photo.width, self.photo.height,
                              self.PHOTO_MAX_WIDTH, new_height,
                              scale))
            self.photo.open('rb')
            img = Image.open(self.photo)
            sized = img.resize((self.PHOTO_MAX_WIDTH, new_height),
                               Image.ANTIALIAS)  
            self.photo.close()
            # save the photo to a buffer in the same format of the original
            buf = StringIO()
            sized.save(buf, img.format)
            # save the contents back to the photo imagefield
            filename = self.photo.name
            # - delete the current photo image but don't update the database yet
            self.photo.delete(save=False)
            # - save the new version with the old filename
            self.photo.save(filename, ContentFile(buf.getvalue()))
            buf.close()


class Degree(models.Model):
    ''':class:`~django.db.models.Model` for a degree held by a user.'''
    holder = models.ForeignKey(UserProfile, verbose_name='Degree holder')
    name = models.CharField(verbose_name='Degree Name',
        max_length=30)
    institution = models.CharField(max_length=255,
        help_text='Institution that granted the degree')
    year = models.IntegerField(blank=True, null=True, default=None) # optional

    def __unicode__(self):
        return ', '.join([self.name, self.institution, self.year])


class Position(models.Model):
    ''':class:`~django.db.models.Model` for an academic title (e.g.: named
    chair, organization president, journal editor) held by a user.'''
    holder = models.ForeignKey(UserProfile, verbose_name='Position holder')
    name = models.CharField(verbose_name='Position Name', max_length=200)

    def __unicode__(self):
        return name


class Grant(models.Model):
    ''':class:`~django.db.models.Model` for a research grant to be displayed
    on a user's profile.'''
    grantee = models.ForeignKey(UserProfile)
    name = models.CharField(max_length=250, blank=True)
    grantor = models.CharField(max_length=250, blank=True)
    project_title = models.CharField(max_length=250, blank=True)
    year = models.IntegerField(blank=True, null=True, default=None)

    def __unicode__(self):
        '''Basic text description of grant, primarily for the admin view
        and/or dev. Probably not useful for the profile display, as that
        will want a bit more complexity and possibly markup.'''
        name = self.name
        if not name and self.grantor:
            name = 'grant from ' + self.grantor
        if not name and self.project_title:
            name = 'grant for ' + self.grantor
        if not name:
            # should be impossible
            name = 'unnamed grant'
        if year:
            name = name + ', ' + str(self.year)
        return name    
        

def researchers_by_interest(name=None, slug=None):
    '''Find researchers by interest.  Returns a QuerySet of
    :class:`~django.contrib.auth.models.User` objects who have the
    specified interest tagged as a research interest on their profile.
    Allows searching by tag name or slug.

    :param name: normal display name of the research interest tag
    :param slug: 
    
    '''
    # filtering on userprofile__research_interests__name fails, but
    # this form seems to work correctly
    tagfilter_prefix = 'userprofile__tagged_items__tag'
    if name:
        filter = {'%s__name' % tagfilter_prefix : name}
    elif slug:
        filter = {'%s__slug' % tagfilter_prefix: slug}
    else:
        raise Exception('Interest tag name or slug required')
    return User.objects.filter(**filter).order_by('last_name')


class Bookmark(models.Model):
    ''':class:`~django.db.models.Model` to allow users to create
    private bookmarks and tags for
    :class:`~eulfedora.models.DigitalObject` instances.
    '''
    user = models.ForeignKey(User)
    ''':class:`~django.contrib.auth.models.User` who created and owns
    this bookmark'''
    pid = models.CharField(max_length=255) 
    '''permanent id of the :class:`~eulfedora.models.DigitalObject` in
    Fedora'''
    tags = TaggableManager()
    ''':class:`taggit.managers.TaggableManager` for tags associated with
    the object'''
    unique_together = ( ('user', 'pid'), )

    def display_tags(self):
        'comma-separated string with all tags'
        # for display in django db-admin
        return ', '.join(self.tags.all().values_list('name', flat=True))


def pids_by_tag(user, tag):
    '''Find the pids of bookmarked objects for a given
    :class:`~django.contrib.auth.models.User` and
    :class:`~taggit.models.Tag`. Returns a list of pids.

    :param user: :class:`~django.contrib.auth.models.User` whose
        :class:`~openemory.accounts.models.Bookmark` objects should be
        searched
    :param tag: :class:`~taggit.models.Tag` tag to filter
        :class:`~openemory.accounts.models.Bookmark` objects
    :returns: list of pids
    '''
    return Bookmark.objects.filter(user=user,
                                   tags=tag).values_list('pid', flat=True)

def articles_by_tag(user, tag):
    '''Find articles in Solr based on a
    :class:`~django.contrib.auth.models.User` and their
    :class:`~openemory.accounts.models.Bookmark` s.
    
    Calls :meth:`pids_by_tag` to find the pids of bookmarked objects
    for the specified user and tag, and then queries Solr to get
    display information for those objects.
    '''
    solr = solr_interface()
    pidfilter = None
    # find any objects with pids bookmarked by the user
    # - generates a filter that looks like Q(pid=pid1) | Q(pid=pid2) | Q(pid=pid3)
    tagged_pids = pids_by_tag(user, tag)
    # if no pids are found, just return an empty list 
    if not tagged_pids:
        return []
    for pid in tagged_pids:
        if pidfilter is None:
            pidfilter = solr.Q(pid=pid)
        else:
            pidfilter |= solr.Q(pid=pid)
    solrquery = solr.query(pidfilter) \
                        .field_limit(ARTICLE_VIEW_FIELDS) \
                        .sort_by('-last_modified')	# best option ?
    
    # return solrquery instead of calling execute so the result can be
    # paginated
    return solrquery


class EsdPerson(models.Model):
    '''A partial user profile from the external read-only ESD database.
    Users may be indexed by ppid or netid.'''

    id = models.AutoField(primary_key=True, db_column='prsn_i', editable=False)
    ppid = models.CharField(max_length=8, db_column='prsn_i_pblc',
            help_text="public person id/directory key")
    directory_name = models.CharField(max_length=75, db_column='prsn_n_full_dtry',
            help_text="full name in the online directory")
    ad_name = models.CharField(max_length=75, db_column='prsn_n_dspl_acdr',
            help_text="name in Active Directory")
    firstmid_name = models.CharField(max_length=20, db_column='prsn_n_fm_dtry',
            help_text="first and middle name in the online directory")
    last_name = models.CharField(max_length=25, db_column='prsn_n_last_dtry',
            help_text="last name in the online directory")
    name_suffix = models.CharField(max_length=15, db_column='prsn_n_sufx_dtry',
            help_text="honorary or other name suffix in the online directory")
    title = models.CharField(max_length=70, db_column='prsn_e_titl_dtry',
            help_text="position title in the online directory")
    phone = models.CharField(max_length=12, db_column='prad_a_tlph_empe_fmtt',
            help_text="phone number in the online directory")
    fax = models.CharField(max_length=12, db_column='prad_a_fax_empe_fmtt',
            help_text="fax number in the online directory")
    department_id = models.CharField(max_length=10, db_column='dprt_c',
            help_text="identifying code of the department the user works in")
    department_name = models.CharField(max_length=40, db_column='dprt8dtry_n',
            help_text="human-readable name of the department the user works in")
    division_code = models.CharField(max_length=10, db_column='dvsn_i',
            help_text="identifying code of the division the user works in")
    division_name = models.CharField(max_length=40, db_column='dvsn8dtry_n',
            help_text="human-readable name of the division the user works in")
    mailstop_code = models.CharField(max_length=12, db_column='mlst_i',
            help_text="identifying code of the user's mailstop")
    mailstop_name = models.CharField(max_length=30, db_column='mlst_n',
            help_text="human-readable name of the user's mailstop")

    netid = models.CharField(max_length=8, db_column='logn8ntwr_i',
            help_text="network login") # always all-caps
    internet_suppressed = YesNoBooleanField(db_column='prsn_f_sprs_intt',
            help_text="suppress user's directory information to off-campus clients")
    directory_suppressed = YesNoBooleanField(db_column='prsn_f_sprs_dtry',
            help_text="suppress user's directory information to all clients")
    information_suppressed = YesNoBooleanField(db_column='prsn_f_sprs_infr',
            help_text="no reference allowed to user")
    faculty_flag = YesNoBooleanField(max_length=1, db_column='empe_f_fclt',
            help_text="user is a faculty member")
    email = models.CharField(max_length=100, db_column='emad_n',
            help_text="user's primary email address")
    email_forward = models.CharField(max_length=100, db_column='emad8frwd_n',
            help_text="internal or external forwarding address for email")

    # choice meanings per email from esd team
    EMPLOYEE_STATUS_CHOICES = (
        ('A', 'active'),
        ('D', 'deceased'),
        ('L', 'on leave'),
        ('O', 'on-boarding'), # ESD's term. not sure what it means
        ('P', 'sponsored'),
        ('T', 'terminated'),
    )
    employee_status = models.CharField(max_length=1, choices=EMPLOYEE_STATUS_CHOICES,
                                       db_column='emjo_c_stts_empe')

    # choice meanings per email from esd team
    PERSON_TYPE_CHOICES = (
        ('A', 'administrative'),
        ('B', 'student/staff'),
        ('C', 'staff/student'),
        ('E', 'staff'),
        ('F', 'faculty'),
        ('J', 'EU job eligible'),
        ('O', 'student applicant'),
        ('P', 'sponsored'),
        ('R', 'retired'),
        ('S', 'student'),
        ('U', 'unknown'),
        ('X', 'pre-start'),
    )
    person_type = models.CharField(max_length=1, db_column='prsn_c_type')

    class Meta:
        db_tablespace = 'esdv'
        # oracle tablespace requires this db_table syntax as of django
        # 1.3.1. mysql interprets it as a table name with quotes and a
        # period in it.
        db_table = '"esdv"."v_oem_fclt"'
        managed=False

    def __unicode__(self):
        return '%s (%s)' % (self.ppid, self.netid)

    @property
    def department_shortname(self):
        if ':' in self.department_name:
            return self.department_name[self.department_name.rfind(':')+1:]
        return self.department_name

    def profile(self):
        '''Find the :class:`UserProfile` corresponding to this
        :class:`EsdPerson`.
        '''
        return UserProfile.objects.get(user__username=self.netid.lower())

    def has_profile_page(self):
        '''Return ``True`` if the user should have a public-facing web
        profile on the site, ``False`` if not.  Currently requires
        Faculty status.
        '''
        return self.person_type == 'F'

