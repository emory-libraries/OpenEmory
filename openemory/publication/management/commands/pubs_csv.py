from django.conf import settings
from collections import defaultdict
import csv
from getpass import getpass
import logging
from optparse import make_option

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.core.paginator import Paginator
from django.utils.encoding import smart_str

from openemory.accounts.models import EsdPerson, UserProfile
from openemory.common import romeo
from openemory.common.fedora import ManagementRepository
from openemory.publication.models import Publication


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    ''' This command run through all the articles and makes sure that journal titles and publishers match against Sherpa Romeo
    '''
    args = "[netid netid ...]"
    help = __doc__

    option_list = BaseCommand.option_list + (
        make_option('--noact', '-n',
                    action='store_true',
                    default=False,
                    help='Fixed all caps title in articles'),
        )

    def handle(self, *args, **options):

        self.verbosity = int(options['verbosity'])    # 1 = normal, 0 = minimal, 2 = all
        self.v_normal = 1


        # connection to repository
        self.repo = ManagementRepository()
        pid_set = self.repo.get_objects_with_cmodel(Publication.ARTICLE_CONTENT_MODEL, type=Publication)
        writer = csv.writer(open("publications_csv.csv", 'wb'))
        writer.writerow([
            smart_str(u"PID"),
            smart_str(u"Title"),
            smart_str(u"Withdrawn"),
            smart_str(u"Authors"),
            smart_str(u"Journal Title"),
            smart_str(u"Publisher"),
            smart_str(u"Version"),
            smart_str(u"Final Published Link"),
            smart_str(u"DOI"),
            smart_str(u"Subjects"),
            smart_str(u"Funding Group"),
            smart_str(u"CC License"),
            smart_str(u"Copyright Statement"),
            smart_str(u"Admin Note"),
            smart_str(u"Date Reviewed"),
            smart_str(u"Rights Research Date"),
            smart_str(u"PMC"),
            smart_str(u"PUBSID"),
            smart_str(u"File Deposited"),

        ])

        try:
            articles = Paginator(pid_set, 100)

        except Exception as e:
            self.output(0, "Error paginating items: : %s " % (e.message))

        #process all Articles
        for p in articles.page_range:
            try:
                objs = articles.page(p).object_list
            except Exception as e:
                #print error and go to next iteration of loop
                self.output(0,"Error getting page: %s : %s " % (p, e.message))
                continue
            for article in objs:
                try:
                    if not article.exists:
                        self.output(0, "Skipping %s because pid does not exist" % article.pid)
                        continue
                    else:
                        mods = article.descMetadata.content
                        symp = article.sympAtom.content
                        authors = []
                        subjects = []
                        funders = []
                        for author in mods.authors:
                            authors.append('%s %s' % (author.given_name, author.family_name))
                        for subject in mods.subjects:
                            subjects.append(subject.topic)
                        for funder in mods.funders:
                            funders.append(funder.name)

                        writer.writerow([
                            smart_str(article.pid if article.pid else ''),
                            smart_str(article.label if article.label else ''),
                            smart_str(article.is_withdrawn),
                            smart_str(",".join(authors)),
                            smart_str(mods.journal.title if mods.journal else ''),
                            smart_str(mods.journal.publisher if mods.journal else ''),
                            smart_str(mods.version if mods.version else ''),
                            smart_str(mods.ark if mods.ark else ''),
                            smart_str(mods.final_version.url if mods.final_version else ''),
                            smart_str(",".join(subjects)),
                            smart_str(",".join(funders)),
                            smart_str(mods.license.text if mods.license else ''),
                            smart_str(mods.copyright.text if mods.copyright else ''),
                            smart_str(mods.admin_note.text if mods.admin_note else ''),
                            smart_str(article.provenance.content.date_reviewed if article.provenance else ''),
                            smart_str(mods.rights_research_date if mods.rights_research_date else ''),
                            smart_str(article.pmcid if article.pmcid else ''),
                            smart_str(symp.pubs_id if symp else ''),
                            smart_str("Yes" if article.pdf.exists else 'No'),


                        ])

                except Exception as e:
                    self.output(0, "Error processing pid: %s : %s " % (article.pid, e.message))
                    # self.counts['errors'] +=1
        writer.close()


    def output(self, v, msg):
        '''simple function to handle logging output based on verbosity'''
        if self.verbosity >= v:
            self.stdout.write("%s\n" % msg)