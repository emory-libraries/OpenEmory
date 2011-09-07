from django.db import models
from django.core.files.base import ContentFile
from django.contrib.auth.models import User
from openemory.harvest.entrez import EntrezClient

class HarvestRecord(models.Model):
    STATUSES = ('harvested', 'ingested', 'ignored')
    STATUS_CHOICES = [(val, val) for val in STATUSES]
    pmcid = models.IntegerField('PubMed Central ID', unique=True, editable=False)
    authors = models.ManyToManyField(User)
    title = models.TextField('Article Title')
    harvested = models.DateTimeField('Date Harvested', auto_now_add=True, editable=False)
    status = models.CharField(choices=STATUS_CHOICES, max_length=25,
                              default=STATUSES[0])
    fulltext = models.BooleanField(editable=False)
    content = models.FileField(upload_to='harvest/%Y/%m/%d')
    # file storage for the full Article XML fetched from PMC
    
    class Meta:
        permissions = (
            # add, change, delete are avilable by default
            ('view_harvestrecord', 'Can see available harvested records'),
        )

    def __unicode__(self):
        return u'%s (PMCID:%d, %s)' % (self.title, self.pmcid, self.status)

    @property
    def access_url(self):
        'Direct link to this PubMed Central article, based on PubMed Central ID.'
        return 'http://www.ncbi.nlm.nih.gov/pmc/articles/PMC%d/' % self.pmcid


    @staticmethod
    def init_from_fetched_article(article):
        '''Initialize a new
        :class:`~openemory.harvest.models.HarvestRecord` instance based
        on information from an
        :class:`~openemory.harvest.entrez.EFetchArticle`.

        :returns: saved :class:`HarvestRecord` instance
        '''

        record = HarvestRecord(title=article.article_title,
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
    

class OpenEmoryEntrezClient(EntrezClient):
    '''Project-specific methods build on top of an
    :class:`~openemory.harvest.entrez.EntrezClient`.
    '''
    # FIXME: This doesn't feel like a "model" per se, but not sure precisely
    # where else it belongs...

    def get_emory_articles(self):
        '''Search Entrez for Emory articles, currently limited to PMC
        articles with "emory" in the affiliation metadata.

        :returns: :class:`~openemory.harvest.entrez.ESearchResponse`
        '''
        search_result = self.esearch(
            usehistory='y', # store server-side history for later queries
            db='pmc',       # search PubMed Central
            term='emory',   # for the term "emory"
            field='affl',   # in the "Affiliation" field
        )
        fetch_result = self.efetch(
            db='pmc',       # search PubMed Central
            usehistory='y', # use stored server-side history
            WebEnv=search_result.webenv,
            query_key=search_result.query_key,
            retstart=0,     # start with record 0
            retmax=20,      # return 20 records
        )
        return fetch_result.articles
