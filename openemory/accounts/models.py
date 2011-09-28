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

    def recent_articles(self, limit=3):
        '''Query Solr to find recent articles by this author.

        :param limit: number of articles to return. (defaults to 3)
        '''
        solr = solr_interface()
        solrquery = solr.query(owner=self.user.username) \
                        .filter(content_model=Article.ARTICLE_CONTENT_MODEL) \
                        .field_limit(ARTICLE_VIEW_FIELDS) \
                        .sort_by('-last_modified')
        results = solrquery.paginate(rows=limit).execute()
        return results


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
