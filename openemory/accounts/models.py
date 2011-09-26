from django.contrib.auth.models import User
from django.db import models
from eullocal.django.emory_ldap.models import AbstractEmoryLDAPUserProfile
from taggit.managers import TaggableManager
from taggit.models import TaggedItem

from openemory.util import solr_interface
from openemory.publication.models import Article

class UserProfile(AbstractEmoryLDAPUserProfile):
    user = models.OneToOneField(User)
    research_interests = TaggableManager()

    def recent_articles(self, limit=3):
        '''Query Solr to find recent articles by this author.

        :param limit: number of articles to return. (defaults to 3)
        '''
        solr = solr_interface()
        solrquery = solr.query(owner=self.user.username).filter(
            content_model=Article.ARTICLE_CONTENT_MODEL).sort_by('-last_modified')
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
