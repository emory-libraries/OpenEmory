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
