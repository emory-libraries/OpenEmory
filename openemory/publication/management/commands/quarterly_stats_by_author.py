from collections import defaultdict
import datetime
import logging
from optparse import make_option

from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand, CommandError
from django.core.urlresolvers import reverse
from django.core.paginator import Paginator
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.template.loader import get_template
from django.template import Context
from openemory import settings

from openemory.publication.models import Article, year_quarter, ArticleStatistics
from openemory.util import solr_interface



logger = logging.getLogger(__name__)

class Command(BaseCommand):
    '''Generates quarterly report by author of views and downloads of each :class:`~openemory.publication.models.Article`
    that a author is associated with using solr and info from :class:`~openemory.publication.models.ArticleStatistics`.
    '''
    args = "[netid netid ...]"
    help = __doc__

    option_list = BaseCommand.option_list + (
        make_option('--noact', '-n',
                    action='store_true',
                    default=False,
                    help='Reports stats for each author but does not send emails'),
        )
    
    def handle(self, *args, **options):
        self.verbosity = int(options['verbosity'])    # 1 = normal, 0 = minimal, 2 = all
        self.v_normal = 1

        #counters for script reporting
        counts = defaultdict(int)

        #Connection to solr
        solr = solr_interface()

        #info today's date will be used to caculate previous quarter
        today = datetime.datetime.today()
        current_year = today.year
        current_month = today.month
        current_quarter = year_quarter(current_month)
        self.output(1, "Current month/year: %s/%s quarter: %s" % (current_month, current_year, current_quarter))

        if current_quarter == 1:
            self.year = current_year -1
            self.quarter = 4
        else:
            self.year = current_year
            self.quarter = current_quarter - 1

        self.output(1, "Report will run for year: %s quarter: %s" % (self.year, self.quarter))

        #start and end dates
        start_end = {
            1 : ('January 1, %s' % self.year, 'March 31, %s' % self.year),
            2 : ('April 1, %s' % self.year, 'June 30, %s' % self.year),
            3 : ('July 1, %s' % self.year, 'September 30, %s' % self.year),
            4 : ('October 1, %s' % self.year, 'December 31, %s' % self.year),
        }




        #if netids specified, use that list
        if len(args) != 0:
            netid_set = list(args)

        else:
            #search for authors with published articles.
            try:
                netid_set = solr.query().filter(content_model=Article.ARTICLE_CONTENT_MODEL,state='A').\
                facet_by('owner').paginate(rows=0).execute()

            except Exception as e:
                if 'is not a valid field name' in e.message:
                    raise CommandError('Solr unknown field error ' +
                                       '(check that local schema matches running instance)')
                raise CommandError('Error (%s)' % e.message)

            #get just the netid and thow away the count
            netid_set = netid_set.facet_counts.facet_fields['owner']
            netid_set = [n[0] for n in netid_set]

        #query solr for all articles for each user
        for n in netid_set:
            self.output(1, "Processing user %s" % n)
            try:
                article_query = solr.query().filter(content_model=Article.ARTICLE_CONTENT_MODEL,state='A' ,
                                                 owner=n).field_limit(['pid', 'title'])
                articles = Paginator(article_query, 5) #change later
                articles = articles.object_list
            except Exception as e:
                self.output.error(0, e.message)
                continue

            article_data = self.get_article_data(articles, self.year, self.quarter)

            #add name and email to article data
            user = User.objects.filter(username=n)
            if user:
                user = user[0] # again should only be 1 record
                article_data['first_name'] = user.first_name
                article_data['last_name'] = user.last_name
                article_data['email'] = user.email
                article_data['start'] = start_end[self.quarter][0]
                article_data['end'] = start_end[self.quarter][1]

                #send the email!
                self.send_mail(article_data, options)


    def get_article_data(self, articles, year, quarter):
        '''
        Generates all stats on articles_list for a user.
        Most of the data is from the associated :class:`~openemory.publication.models.ArticleStatistics` object.

        :param articles_list: a list of dicts containing pid and title for each article for a user.
        :param year: int year the stats are from.
        :param quarter: int quarter of the year the stats are from.

        :returns: dict of dicts containing title, views, download,
        link to article and total views and downloads.
        '''
        domain = Site.objects.get_current().domain
        all_data = dict()
        articles_list = list()
        all_views = 0
        all_downloads = 0

        for a in articles:
            self.output(2, "Getting info for Article %s(%s)" % (a['title'], a['pid']))
            article_data = dict()
            stats = ArticleStatistics.objects.filter(pid=a['pid'], year=year, quarter=quarter)
            if stats:
                stats = stats[0] #should onlybe 1 record
                article_data['views'] = stats.num_views
                article_data['downloads'] = stats.num_downloads
                all_views += stats.num_views
                all_downloads += stats.num_downloads
            else:
                article_data['views'] = 0
                article_data['downloads'] = 0

            #add in the rest of the data and add to list to return
            article_data['title'] = a['title']
            article_data['url'] = "http://%s%s" % (domain, reverse("publication:view", kwargs={'pid': a['pid']}))
            articles_list.append(article_data)



        #add total stats and lsit to return
        all_data['all_views'] = all_views
        all_data['all_downloads'] = all_downloads
        all_data['articles_list'] = articles_list
        return all_data


    def send_mail(self, data, options):
        list_serve_email = "openemory@listserv.cc.emory.edu"
        sender = "OpenEmory Administrator <%s>" % (list_serve_email)

        # add list serve email to context
        data['list_serve_email'] = list_serve_email

        #create plain text content
        t = get_template("publication/email/quarterly_report.txt")
        text = t.render(Context(data))

        #create html content
        t = get_template("publication/email/quarterly_report.html")
        html = t.render(Context(data))

        #send mail
        msg = EmailMultiAlternatives("OpenEmory Quarterly Statistics for Your Articles",
                                     text, sender, [data['email']])
        msg.attach_alternative(html, "text/html")

        if not options['noact']:
            msg.send()
            self.output(1, "Mail Sent")
        else:
            self.output(1, "No Mail Sent")


    def output(self, v, msg):
        '''simple function to handle logging output based on verbosity'''
        if self.verbosity >= v:
            self.stdout.write("%s\n" % msg)
