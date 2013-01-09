from collections import defaultdict
from getpass import getpass
import logging
from optparse import make_option

from django.core.management.base import BaseCommand, CommandError
from django.core.paginator import Paginator

from eulfedora.server import Repository

from openemory.publication.models import Article
from openemory.util import solr_interface

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    '''Fetch article data from solr for `~openemory.publication.models.Article` objects with dsid contentMetadata.
     If content is empyt remove the datastream, else copy the licensinfo into the MODS.  If PIDs are
    provided in the arguments, that list of pids will be used instead of searching solr.
    '''
    args = "[pid pid ...]"
    help = __doc__

    option_list = BaseCommand.option_list + (
        make_option('--noact', '-n',
                    action='store_true',
                    default=False,
                    help='Reports the pid and total number of Articles that would be processed but does not really do anything.'),
        make_option('--username',
                    action='store',
                    help='Username of fedora user to connect as'),
        make_option('--password',
                    action='store',
                    help='Password for fedora user,  password=  will prompt for password'),
        )


    
    def handle(self, *args, **options):
        self.verbosity = int(options['verbosity'])    # 1 = normal, 0 = minimal, 2 = all
        self.v_normal = 1

        #counters
        counts = defaultdict(int)

        # check required options
        if not options['username']:
            raise CommandError('Username is required')
        else:
            if not options['password'] or options['password'] == '':
                options['password'] = getpass()

        #connection to repository
        repo = Repository(username=options['username'], password=options['password'])

        #Connection to solr
        solr = solr_interface()

        #if pids specified, use that list
        if len(args) != 0:
            pid_set = list(args)
            #convert list into dict so both solr and pid list formats are the same
            pid_set = [{'pid' : pid} for pid in pid_set]

        else:
            #search for Articles with a contentMetadata DS.
            # Only return the pid for each record.
            try:
                pid_set = solr.query().filter(content_model=Article.ARTICLE_CONTENT_MODEL, dsids='contentMetadata').\
                                             field_limit('pid')

            except Exception as e:
                if 'is not a valid field name' in e.message:
                    raise CommandError('Solr unknown field error ' +
                                       '(check that local schema matches running instance)')
                raise CommandError('Error (%s)' % e.message)

        try:
            articles = Paginator(pid_set, 20)
            counts['total'] = articles.count
        except Exception as e:
            self.output(0, "Error paginating items: : %s " % (e.message))

        #process all Articles
        for p in articles.page_range:
            try:
                objs = articles.page(p).object_list
            except Exception as e:
                #print error and go to next iteration of loop
                self.output(0,"Error getting page: %s : %s " % (p, e.message))
                counts['errors'] +=1
                continue
            for obj in objs:
                try:
                    article = repo.get_object(type=Article, pid=obj['pid'])
                    if not article.exists:
                        self.output(1, "Skipping %s because pid does not exist" % obj['pid'])
                        counts['skipped'] +=1
                        continue
                    else:
                        self.output(0,"Processing %s" % article.pid)
                        if article.contentMetadata.content.is_empty():
                            self.output(1,"Removing contentMetadata for %s" % article.pid)
                            if not options['noact']:
                                article.api.purgeDatastream(article.pid, 'contentMetadata', logMessage='Removing empty datastream')
                            counts['removed'] += 1
                        elif article.contentMetadata.content.license:
                            self.output(1,"Copying license info to MODS for %s" % article.pid)
                            article.descMetadata.content.create_license()
                            article.descMetadata.content.license.text = article.contentMetadata.content.license.text
                            article.descMetadata.content.license.link = article.contentMetadata.content.license.link
                            if not options['noact']:
                                article.save("Updated MODS with license info")
                            counts['mod'] += 1
                        else:
                            self.output(1, "Skipping %s because license info does not exist" % obj['pid'])
                            counts['skipped'] +=1
                except Exception as e:
                    self.output(0, "Error processing pid: %s : %s " % (obj['pid'], e.message))
                    counts['errors'] +=1

        # summarize what was done
        self.stdout.write("Total number selected: %s\n" % counts['total'])
        self.stdout.write("Removed: %s\n" % counts['removed'])
        self.stdout.write("Modified: %s\n" % counts['mod'])
        self.stdout.write("Skipped: %s\n" % counts['skipped'])
        self.stdout.write("Errors: %s\n" % counts['errors'])


    def output(self, v, msg):
        '''simple function to handle logging output based on verbosity'''
        if self.verbosity >= v:
            self.stdout.write("%s\n" % msg)
