from django.db import models
from openemory.harvest.entrez import EntrezClient

class HarvestRecord(models.Model):
    # place-holder db model for now, for permissions hook
    class Meta:
        permissions = (
            # add, change, delete are avilable by default
            ('view_harvestrecord', 'Can see available harvested records'),
        )


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
        return self.esearch(
            db='pmc',     # search PubMed Central
            term='emory', # for the term "emory"
            field='affl', # in the "Affiliation" field
        )
