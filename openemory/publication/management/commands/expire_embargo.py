from collections import defaultdict
import datetime
import logging
from optparse import make_option

from django.core.management.base import BaseCommand, CommandError
from django.core.paginator import Paginator

from eulfedora.server import Repository

from openemory.publication.models import Article
from openemory.util import solr_interface

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    '''Fetch article data from solr for `~openemory.publication.models.Article` objects with expired
    embargoes, then reindex the item so that the full text will be visible and searchable. If PIDs are
    provided in the arguments, that list of pids will be used instead of searching solr.
    '''
    args = "[pid pid ...]"
    help = __doc__

    option_list = BaseCommand.option_list + (
        make_option('--noact', '-n',
                    action='store_true',
                    default=False,
                    help='Reports the pid and total number of Articles that would be processed but does not reindex them.'),
        )
    
    def handle(self, *args, **options):
        self.verbosity = int(options['verbosity'])    # 1 = normal, 0 = minimal, 2 = all
        self.v_normal = 1

        #counters
        counts = defaultdict(int)

        #connection to repository
        #uses default user / pass configured in localsettings.py
        repo = Repository()

        #Connection to solr
        solr = solr_interface()

        #todays date in the same format as embargo_end date
        today = datetime.datetime.now().strftime("%Y-%m-%d")

        #if pids specified, use that list
        if len(args) != 0:
            pid_set = list(args)
            #convert list into dict so both solr and pid list formats are the same
            pid_set = [{'pid' : pid} for pid in pid_set]

        else:
            #search for active Articles with an embargo_end date less than today,
            # and that do not have fulltext field indexed. Only return the pid for each record.
            try:
                pid_set = solr.query().filter(content_model=Article.ARTICLE_CONTENT_MODEL,
                                                         state='A', embargo_end__lt=today).exclude(fulltext__any=True).\
                                                         field_limit('pid')

            except Exception as e:
                if 'is not a valid field name' in e.message:
                    raise CommandError('Solr unknown field error ' +
                                       '(check that local schema matches running instance)')
                raise CommandError('Error (%s)' % e.message)

        try:
            expired_embargoes = Paginator(pid_set, 20)
            counts['total'] = expired_embargoes.count
        except Exception as e:
            self.output(0, "Error paginating items: : %s " % (e.message))

        #process all expired embargoes
        for p in expired_embargoes.page_range:
            try:
                objs = expired_embargoes.page(p).object_list
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
                    #do not try to index items without valid fulltext field
                    data = article.index_data()
                    if 'fulltext' in data and data['fulltext'] != None and data['fulltext'].strip():
                        self.output(1,"Processing %s" % article.pid)
                        if not options['noact']:
                           solr.add(data)
                           counts['indexed'] +=1
                    else:
                        self.output(1, "Skipping %s because fulltext does not exist" % article.pid)
                        counts['skipped'] +=1
                except Exception as e:
                    self.output(0, "Error processing pid: %s : %s " % (obj['pid'], e.message))
                    counts['errors'] +=1

        # summarize what was done
        self.stdout.write("Total number selected: %s\n" % counts['total'])
        self.stdout.write("Indexed: %s\n" % counts['indexed'])
        self.stdout.write("Skipped: %s\n" % counts['skipped'])
        self.stdout.write("Errors: %s\n" % counts['errors'])


    def output(self, v, msg):
        '''simple function to handle logging output based on verbosity'''
        if self.verbosity >= v:
            self.stdout.write("%s\n" % msg)
