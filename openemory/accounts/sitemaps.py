# file openemory/accounts/sitemaps.py
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

from django.contrib.sitemaps import Sitemap
from django.core.urlresolvers import reverse
from openemory.accounts.models import EsdPerson

class ProfileSitemap(Sitemap):
    # NOTE: disabling change frequency since it could be highly variable,
    # changefreq = 'monthly'

    def items(self):
        # FIXME: handle nonfaculty with profiles
        return EsdPerson.faculty.all()

    def location(self, esd):
        return reverse('accounts:profile',
                       kwargs={'username': esd.netid.lower()})
