# file openemory/harvest/models.py
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

from django.db import models
from django.core.files.base import ContentFile
from django.contrib.auth.models import User
from eulfedora.server import Repository
from eulxml.xmlmap import load_xmlobject_from_string, load_xmlobject_from_file
from openemory.harvest.entrez import EntrezClient, ArticleQuerySet
from openemory.publication.models import Publication, NlmArticle, Article
from openemory.util import pmc_access_url
import  logging

logger = logging.getLogger(__name__)

class HarvestRecord(models.Model):
    STATUSES = ('harvested', 'inprocess', 'ingested', 'ignored')
    DEFAULT_STATUS = STATUSES[0]
    STATUS_CHOICES = [(val, val) for val in STATUSES]
    pmcid = models.IntegerField('PubMed Central ID', unique=True, editable=False)
    authors = models.ManyToManyField(User)
    title = models.TextField('Article Title')
    harvested = models.DateTimeField('Date Harvested', auto_now_add=True, editable=False)
    status = models.CharField(choices=STATUS_CHOICES, max_length=25,
                              default=DEFAULT_STATUS)
    fulltext = models.BooleanField(editable=False)
    content = models.FileField(upload_to='harvest/%Y/%m/%d', blank=True)
    # file storage for the full Article XML fetched from PMC
    # TODO: content file should be removed when record is ingested or ignored
    
    class Meta:
        permissions = (
            # add, change, delete are avilable by default
            ('ingest_harvestrecord', 'Can ingest harvested record to Fedora'),
            ('ignore_harvestrecord', 'Can mark a harvested record as ignored')
        )

    def __unicode__(self):
        return u'%s (PMC%d, %s)' % (self.title, self.pmcid, self.status)

    @property
    def access_url(self):
        'Direct link to this PubMed Central article, based on PubMed Central ID.'
        return pmc_access_url(self.pmcid)

    def mark_in_process(self):
        '''Mark this record as in process for ingest by another process to
        minimize the chances of accidentally ingesting an object twice.'''
        self.status = 'inprocess'
        self.save()

    def mark_ingested(self):
        '''Mark this record as ingested into the repository.  Updates
        the status and removes the harvestd Article xml file.'''
        self.status = 'ingested'
        if self.content:
            self.content.delete()
        self.save()

    @property
    def ingestable(self):
        '''Boolean; indicates of this record is in an accetable status
        for ingest.?'''
        # don't allow ingesting records that have already been
        # ingested or marked as ignored
        return self.status == 'harvested'

    def mark_ignored(self):
        '''Mark this record as ignored (will not be ingested into the
        repository0.  Updates the status and removes the harvestd
        Article xml file.'''
        self.status = 'ignored'
        if self.content:
            self.content.delete()
        self.save()


    @staticmethod
    def init_from_fetched_article(article):
        '''Initialize a new
        :class:`~openemory.harvest.models.HarvestRecord` instance based
        on information from an
        :class:`~openemory.publication.models.NlmArticle`.

        :returns: saved :class:`HarvestRecord` instance
        '''

        # article StringField attributes are unicode-like objects, not true
        # unicode objects. some database layers (notably mysql) try to turn
        # them into strings, failing on non-ascii data. convert them
        # explicitly into real unicode objects here before passing them into
        # the db later to avoid this problem.
        record = HarvestRecord(title=unicode(article.article_title),
                               pmcid=article.docid,
                               fulltext=article.fulltext_available)
        if article.identifiable_authors():
            # record must be saved before we can add relation to authors
            record.save()
            record.authors = article.identifiable_authors()

        # save article xml as a file associated with this record
        record.content.save('%d.xml' % article.docid,
                            ContentFile(article.serialize(pretty=True)))
        record.save()
        return record


    def as_publication_article(self, repo=None):
        '''Initialize (but do not save) a new
        :class:`~openemory.publication.models.Article` instance and
        based on harvested record information and Article XML.

        :param repo: optional; pass in an existing
           :class:`eulfedora.server.Repository` object initialized
           with the desired credentials

        :returns: unsaved :class:`~openemory.publication.models.Article`
        '''
        if repo is None:
            repo = Repository()
        article = repo.get_object(type=Article)
        # using comma-delimited usernames to indicate object has multiple owners
        # should work with existing XACML owner policy;
        # for more detail, see https://jira.duraspace.org/browse/FCREPO-82
        article.owner = ', '.join(auth.username for auth in self.authors.all())
        # VERY preliminary, minimal metadata mapping 
        article.label = self.title
        article.dc.content.title = self.title
        article.dc.content.creator_list.extend([auth.get_full_name()
                                                for auth in self.authors.all()])
        article.dc.content.identifier_list.extend([self.access_url,
                                               'PMC%d' % self.pmcid])

        # set the XML article content as the contentMetadata datastream
        # - record content is a file field with a read method, which should be
        #   handled correctly by eulfedora for ingest
        if hasattr(self.content, 'read'):
            article.contentMetadata.content = load_xmlobject_from_file(self.content, NlmArticle)

        if article.contentMetadata.content:
            article.descMetadata.content = article.contentMetadata.content.as_article_mods()

            
        # FIXME: datastream checksum!
        # TODO: format uri for this datastream ? 

        return article
    

class OpenEmoryEntrezClient(EntrezClient):
    '''Project-specific methods build on top of an
    :class:`~openemory.harvest.entrez.EntrezClient`.
    '''
    # FIXME: This doesn't feel like a "model" per se, but not sure precisely
    # where else it belongs...

    def get_emory_articles(self, **kwargs):
        '''Search Entrez for Emory articles, currently limited to PMC
        articles with "emory" in the affiliation metadata.

        :returns: :class:`~openemory.harvest.entrez.ESearchResponse`
        '''
        # basic args for query
        qargs = {
            'usehistory' : 'y', # store server-side history for later queries
            'db' : 'pmc',       # search PubMed Central
            'term': 'emory',   # for the term "emory"
            'field': 'affl'   # in the "Affiliation" field
        }

        #add any addition args for query
        qargs.update(kwargs)

        search_result = self.esearch(**qargs)
        qs = ArticleQuerySet(self, search_result, 
            db='pmc',       # search PubMed Central
            usehistory='y', # use stored server-side history
            WebEnv=search_result.webenv,
            query_key=search_result.query_key,
        )
            
        return qs
