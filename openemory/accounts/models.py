from django.contrib.auth.models import User
from django.db import models
from eullocal.django.emory_ldap.models import AbstractEmoryLDAPUserProfile
from taggit.managers import TaggableManager
from taggit.models import TaggedItem

from openemory.util import solr_interface
from openemory.publication.models import Article
from openemory.publication.views import ARTICLE_VIEW_FIELDS

class UserProfile(AbstractEmoryLDAPUserProfile):
    user = models.OneToOneField(User)
    research_interests = TaggableManager()

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

