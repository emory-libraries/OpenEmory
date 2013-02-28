# file openemory/common/fedora.py
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

from django.conf import settings
from django.core.urlresolvers import reverse
from django.contrib.sites.models import Site
from django.utils.encoding import iri_to_uri


from eulfedora import models
from pidservices.clients import parse_ark
from pidservices.djangowrapper.shortcuts import DjangoPidmanRestClient


logger = logging.getLogger(__name__)


def absolutize_url(local_url):
    '''Convert a local url to an absolute url, with scheme and server name,
    based on the current configured :class:`~django.contrib.sites.models.Site`.

    :param local_url: local url to be absolutized, e.g. something generated by
        :meth:`~django.core.urlresolvers.reverse`
    '''

    #when used in staging or production the webserver should
    #redirect to https if needed
    if local_url.startswith('http'):
        return local_url

    # add scheme and server (i.e., the http://example.com) based
    # on the django Sites infrastructure.
    root = Site.objects.get_current().domain
    # but also add the http:// if necessary, since most sites docs
    # suggest using just the domain name
    if not root.startswith('http'):
        root = 'http://' + root
    return root + local_url


# try to configure a pidman client to get pids.
try:
    pidman = DjangoPidmanRestClient()
except:
    # if we're in dev mode then we can fall back on the fedora default
    # pid allocator. in non-dev, though, we really need pidman
    if getattr(settings, 'DEV_ENV', False):
        logger.warn('Failed to configure PID manager client; default pid logic will be used')
        pidman = None
    else:
        raise

class DigitalObject(models.DigitalObject):
    """Extend the default fedora DigitalObject class."""

    def __init__(self, *args, **kwargs):
        default_pidspace = getattr(settings, 'FEDORA_PIDSPACE', None)
        kwargs['default_pidspace'] = default_pidspace
        super(DigitalObject, self).__init__(*args, **kwargs)
        self._default_target_data = None

    PID_TOKEN = '{%PID%}'
    ENCODED_PID_TOKEN = iri_to_uri(PID_TOKEN)
    def get_default_pid(self):
        '''Default pid logic for DigitalObjects in openemory.  Mint a
        new ARK via the PID manager, store the ARK in the MODS
        metadata (if available) or Dublin Core, and use the noid
        portion of the ARK for a Fedora pid in the site-configured
        Fedora pidspace.'''
                
        if pidman is not None:
            # pidman wants a target for the new pid
            '''Get a pidman-ready target for a named view.'''

            # first just reverse the view name.
            pid = '%s:%s' % (self.default_pidspace, self.PID_TOKEN)
            target = reverse("publication:view", kwargs={'pid': pid})
            # reverse() encodes the PID_TOKEN, so unencode just that part
            target = target.replace(self.ENCODED_PID_TOKEN, self.PID_TOKEN)
            # reverse() returns a full path - absolutize so we get scheme & server also
            target = absolutize_url(target)
            # pid name is not required, but helpful for managing pids
            pid_name = self.label
            # ask pidman for a new ark in the configured pidman domain
            ark_uri = pidman.create_ark(settings.PIDMAN_DOMAIN, target, name=pid_name)
            # pidman returns the full, resolvable ark
            # parse into dictionary with nma, naan, and noid
            parsed_ark = parse_ark(ark_uri)
            naan = parsed_ark['naan']  # name authority number
            noid = parsed_ark['noid']  # nice opaque identifier
            ark =  "ark:/%s/%s" % (naan, noid)

            # Add full uri ARK to dc:identifier and  descMetadata
            self.dc.content.identifier_list.append(ark_uri)
            self.descMetadata.content.ark_uri = ark_uri
            self.descMetadata.content.ark = ark
            
            # use the noid to construct a pid in the configured pidspace
            return '%s:%s' % (self.default_pidspace, noid)
        else:
            # if pidmanager is not available, fall back to default pid behavior
            return super(DigitalObject, self).get_default_pid()

    @property
    def noid(self):
        pidspace, noid = self.pid.split(':')
        return noid