from eulfedora.models import DigitalObject, FileDatastream


class Article(DigitalObject):
    '''Subclass of :class:`~eulfedora.models.DigitalObject` to
    represent Scholarly Articles.
    
    Following `Hydra content model`_ conventions where appropriate;
    similar to the generic simple Hydra content model
    `genericContent`_.

    .. _Hydra content model: https://wiki.duraspace.org/display/hydra/Hydra+objects%2C+content+models+%28cModels%29+and+disseminators
    .. _genericContent: https://wiki.duraspace.org/display/hydra/Hydra+objects%2C+content+models+%28cModels%29+and+disseminators#Hydraobjects%2Ccontentmodels%28cModels%29anddisseminators-genericContent
    '''
    ARTICLE_CONTENT_MODEL = 'info:fedora/emory-control:PublishedArticle-1.0'
    CONTENT_MODELS = [ ARTICLE_CONTENT_MODEL ]
    
    pdf = FileDatastream('content', 'PDF content', defaults={
        'mimetype': 'application/pdf',
        'versionable': True
        })
    '''PDF content of a scholarly article, stored and accessed as a
    :class:`~eulfedora.models.FileDatastream`; datastream is
    configured to be versioned and managed; default mimetype is
    ``application/pdf``.'''
    

