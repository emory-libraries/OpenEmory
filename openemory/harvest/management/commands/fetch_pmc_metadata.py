# file openemory/harvest/management/commands/fetch_pmc_metadata.py
# 
#   Copyright 2010 , 2011, 2012, 2013 Emory University General Library
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

from collections import defaultdict
import logging
from optparse import make_option
import os

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Max
from django.core.paginator import Paginator
from eulxml import xmlmap

from openemory.harvest.entrez import EFetchResponse
from openemory.harvest.models import OpenEmoryEntrezClient, HarvestRecord
from datetime import datetime, timedelta
from progressbar import ETA, Percentage, ProgressBar, Bar

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    '''Fetch article metadata from PubMed Central, focusing on articles
    affiliated with Emory authors.

    This command connects to PubMed Central via its public web interface and
    finds articles that include Emory in their "Affiliation" metadata.
    '''
    help = __doc__

    option_list = BaseCommand.option_list + (
        make_option('--simulate', '-n',
                    action='store_true',
                    default=False,
                    help='Simulate querying for articles ' +
                    '(use local static fixture response for testing/development)'),
        make_option('--count', '-c',
                    type='int',
                    default=20,
                    help='Number of Articles in a chunk to process at a time.'),
        make_option('--max-articles', '-m',
                    default=None,
                    help='Number of articles to harvest. If not specified, all available are harvested.'),
        make_option('--min-date',
                    default=None,
                    help='''Search for records added on or after this date. Format YYYY/MM/DD.
                            When specified, max-date is required'''),
        make_option('--max-date',
                    default=None,
                    help='''Search for records added on or before this date. Format YYYY/MM/DD
                            When specified, min-date is required'''),
        make_option('--auto-date',
                    action='store_true',
                    default=False,
                    help='Calculate min and max dates based on most recently harvested records'),
        make_option('--progress',
                    action='store_true',
                    default=False,
                    help='Displays a progress bar based on remaining records to process. If used with max-articles the process my finish earlier.'),
        )
    
    def handle(self, *args, **options):
        self.verbosity = int(options['verbosity'])    # 1 = normal, 0 = minimal, 2 = all
        # number of articles we want to harvest in this run
        self.max_articles = int(options['max_articles']) if options['max_articles'] else None

        self.min_date = options['min_date']
        self.max_date = options['max_date']
        self.auto_date = options['auto_date']
        self.v_normal = 1

        stats = defaultdict(int)
        done= False
        chunks, count = self.article_chunks(**options)

        if options['progress']:
            pbar = ProgressBar(widgets=[Percentage(), ' ', ETA(),  ' ', Bar()], maxval=count).start()
        for article_chunk in chunks:
            if self.verbosity > self.v_normal:
                self.stdout.write('Starting article chunk.\n')

            for article in article_chunk:
                stats['articles'] += 1

                if self.verbosity > self.v_normal:
                    # python2.6 fails with ascii encoding errors (on unicode
                    # titles) unless we explicitly encode output to
                    # sys.stdout.write
                    msg = u'Processing [%s] "%s"\n' % \
                          (article.docid, article.article_title)
                    self.stdout.write(msg.encode(self.stdout.encoding))
                
                if HarvestRecord.objects.filter(pmcid=article.docid).exists():
                    if self.verbosity >= self.v_normal:
                        self.stdout.write('[%s] has already been harvested; skipping\n' \
                                          % (article.docid,))
                    continue
                    
                if article.identifiable_authors():
                    try:
                        HarvestRecord.init_from_fetched_article(article)
                        stats['harvested'] += 1
                        if self.max_articles and stats['harvested'] >= self.max_articles:
                            done = True
                            break
                    except Exception as err:
                        self.stdout.write('Error creating record from article: %s\n' % err)
                        stats['errors'] += 1
                        
                else:
                    if self.verbosity >= self.v_normal:
                        self.stdout.write('[%s] has no identifiable authors; skipping\n' \
                                          % (article.docid,))
                    stats['noauthor'] += 1

                if options['progress']:
                    pbar.update(stats['articles'])
            if done:
                if self.verbosity > self.v_normal:
                    self.stdout.write('Harvested %s articles ... stopping \n' % stats['harvested'])
                break
        if options['progress']:
            pbar.finish()

        # summarize what was done
        self.stdout.write('\nArticles processed: %(articles)d\n' % stats)
        if stats['harvested']:
            self.stdout.write('Articles harvested: %(harvested)d\n' % stats)
        if stats['errors']:
            self.stdout.write('Errors harvesting articles: %(errors)d\n' % stats)
        if stats['noauthor']:
            self.stdout.write('Articles skipped (no identifiable authors): %(noauthor)d\n' % stats)

    def article_chunks(self, simulate, count, **kwargs):
        if simulate:
            # simulation mode requested; load fixture response
            if self.verbosity >= self.v_normal:
                self.stdout.write('Simulation mode requested; using static fixture content\n')
            return (self.simulated_response(), self.simulated_response().count())
        else:
            date_opts = self._date_opts(self.min_date, self.max_date, self.auto_date)
            entrez = OpenEmoryEntrezClient()
            qs = entrez.get_emory_articles(**date_opts)
            return (self._page_results(qs, count), qs.count())


    def simulated_response(self):
        article_path = os.path.join(os.path.dirname(__file__), '..',
            '..', 'fixtures', 'efetch-retrieval-from-hist.xml')
        fetch_response = xmlmap.load_xmlobject_from_file(article_path,
                                                         xmlclass=EFetchResponse)
        yield fetch_response.articles

    def _page_results(self, qs, count):
        paginator = Paginator(qs, count)
        for i in paginator.page_range:
            page = paginator.page(i)
            yield page.object_list


    def _date_opts(self, min_date, max_date, auto_date):
        '''
        Ensure that datetype, mindate and max date are set correctly
        :param min_date: earliest date to query for
        :param max_date: latest date to query for
        :param auto_date: if specified caculates min and max dates from database
        '''
        date_args = {}

        if auto_date:
            min = datetime.strftime(HarvestRecord.objects.all().aggregate(Max('harvested'))['harvested__max'], '%Y/%m/%d')
            max = datetime.strftime(datetime.now()+ timedelta(1),'%Y/%m/%d')
            date_args['mindate'] = min
            date_args['maxdate'] = max

        else:
            if min_date or max_date:
                # have to have both min and max date if one is used
                if not (min_date and max_date):
                    raise CommandError("Min Date and Max Date must be used together")
                try:
                    datetime.strptime(min_date, '%Y/%m/%d')
                    date_args['mindate'] = min_date
                except:
                    raise CommandError('Min Date not valid')
                try:
                    datetime.strptime(max_date, '%Y/%m/%d')
                    date_args['maxdate'] = max_date
                except:
                    raise CommandError("Max Date not valid")
                if datetime.strptime(max_date, '%Y/%m/%d') < datetime.strptime(min_date, '%Y/%m/%d'):
                    raise CommandError("Max date must be greter than Min date")
        if date_args:
            date_args['datetype'] = 'edat'
        return date_args