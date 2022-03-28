from django.conf import settings
from collections import defaultdict
from getpass import getpass
import logging
from optparse import make_option

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.core.paginator import Paginator

from openemory.accounts.models import EsdPerson, UserProfile
from openemory.common import romeo
from openemory.common.fedora import ManagementRepository
from openemory.publication.models import Publication


JOURNAL_LIST = ['Acs Medicinal Chemistry Letters','Acs Nano','Acta Physiologica Sinica','Bmc Psychiatry',
                'Acta Psychologica','Aids Care','Aids Patient Care And Stds','Aids Research And Human Retroviruses',
                'Ajp - Renal Physiology','Alcoholism: Clinical and Experimental Research',
                "Alzheimer's Research and Therapy","American Journal of Alzheimer's Disease and Other Dementias",
                "American Journal of Hematology",'American Journal of Human Biology','American Journal of Human Genetics',
                'American Journal of Medical Genetics Part A','American Journal of Medical Genetics Part B: Neuropsychiatric Genetics',
                'American Journal of Nephrology','American Journal of Pathology','American Journal of Physiology - Cell Physiology',
                'American Journal of Physiology - Gastrointestinal and Liver Physiology','American Journal of Physiology - Heart and Circulatory Physiology',
                'American Journal of Physiology - Regulatory, Integrative and Comparative Physiology','American Journal of Respiratory Cell and Molecular Biology',
                'American Journal of the Medical Sciences','American Journal of Transplantation','American Journal of Tropical Medicine and Hygiene',
                'Angewandte Chemie','Annals of Applied Statistics','Annals of cardiothoracic surgery','Annals of Neurology','Annals of the New York Academy of Sciences',
                'Annals of translational medicine','Antimicrobial Agents and Chemotherapy','Antioxidants and Redox Signaling','Applied and Environmental Microbiology',
                'Archives of Biochemistry and Biophysics','Archives of Ophthalmology','Archives of Pathology and Laboratory Medicine','Arteriosclerosis, Thrombosis, and Vascular Biology',
                'Asn Neuro','Biochemical and Biophysical Research Communications','Biology of Blood and Marrow Transplantation','Biomed Research International','Biomedical Engineering Online',
                'Bioorganic and Medicinal Chemistry Letters','Biosecurity and Bioterrorism : Biodefense Strategy, Practice, and Science','Bmc Cancer','Bmc Cell Biology','Bmc Ear, Nose And Throat Disorders',
                'Bmc Infectious Diseases','Bmc International Health And Human Rights','Bmc Medical Genetics','Bmc Medical Informatics And Decision Making','Bmc Medicine',
                'Bmc Neuroscience','Bmc Public Health','Bmc Research Notes','Bmc Systems Biology','Bmj Open','Bmj','Brain, Behavior, and Immunity','British Journal of Ophthalmology',
                'Cbe-Life Sciences Education','Cell Death and Differentiation','Cell Host and Microbe','Clinical and Experimental Immunology','Clinical and Vaccine Immunology','Dementia and Geriatric Cognitive Disorders','Epilepsy and Behavior','Ethnicity and Disease',
                'European Journal of Clinical Nutrition','Faseb Journal','Free Radical Biology and Medicine','Frontiers in Bioscience','Frontiers in Cellular Neuroscience','Frontiers in Evolutionary Neuroscience',
                'Frontiers in Human Neuroscience','Frontiers in Immunology','Frontiers in Microbiology','Frontiers in Neuroanatomy','Frontiers in Neuroengineering','Frontiers in Neuroinformatics',
                'Frontiers in Neurology','Frontiers in Neuroscience','Frontiers in Physiology','Frontiers in Psychology','Genes and Development','Genetics in Medicine','Head and Neck','Health and Quality of Life Outcomes',
                'Hormones and Behavior','Ieee Transactions On Biomedical Engineering','Ieee Transactions On Information Technology In Biomedicine','International Journal of Drug Policy',
                'International Journal of Environmental Research and Public Health','International Journal of Epidemiology','International Journal of Hepatology','International Journal of Molecular Imaging',
                'International Journal of Surgical Oncology','Jama Ophthalmology','Jmir Research Protocols','Journal of Acquired Immune Deficiency Syndromes','Journal of Adolescent Health',
                'Journal of Affective Disorders','Journal of AIDS and Clinical Research',"Journal of Alzheimer's Disease",'Journal of Biological Chemistry','Journal of Biomolecular Screening','Journal of Cardiovascular Magnetic Resonance',
                'Journal of Cardiovascular Nursing','Journal of Cell Biology','Journal of Cell Science','Journal of Cellular and Molecular Medicine','Journal of Cerebral Blood Flow & Metabolism',
                'Journal of Clinical Imaging Science','Journal of Clinical Investigation','Journal of Clinical Microbiology','Journal of Clinical Oncology','Journal of Clinical Psychiatry','Journal of Community Health',
                'Journal of Comparative Neurology','Journal of Comparative Psychology','Journal of Controlled Release','Journal of Diabetes Science and Technology','Journal of Drug Issues','Journal of Experimental Medicine',
                'Journal of Exposure Science and Environmental Epidemiology','Journal of Immunology','Journal of Medical Genetics','Journal of Medical Internet Research','Journal of Medicinal Chemistry','Journal of Molecular Biology',
                'Journal of Molecular Medicine','Journal of Neurochemistry','Journal of Neurodevelopmental Disorders','Journal of Neuroendocrinology','Journal of Neuroinflammation','Journal of Neuroscience Methods',
                'Journal of Neuroscience','Journal of Nuclear Cardiology','Journal of Nuclear Medicine','Journal of Obesity','Journal of Ocular Pharmacology and Therapeutics',
                'Journal of Oncology Practice','Journal of Organic Chemistry','Journal of Pediatric Psychology','Journal of Physical Chemistry B','Journal of Physiology','Journal of Proteome Research','Journal of Psychiatric Research',
                'Journal of the American Academy of Dermatology','Journal of the American Association for Laboratory Animal Science','Journal of the American Chemical Society','Journal of the American College of Cardiology','Journal of the American College of Surgeons',
                'Journal of the American Heart Association','Journal of the American Medical Association','Journal of the American Medical Informatics Association','Journal of the American Society of Nephrology','Journal of the International AIDS Society',
                'Journal of Thoracic Oncology','Journal of Thrombosis and Haemostasis','Journal of Translational Medicine','Journal of Virology',"Journal of Women's Health",
                'mBio','Methods in Molecular Biology','Molecular and Cellular Biology','Molecular and Cellular Neuroscience','Molecular Biology and Evolution','Molecular Biology of the Cell',
                'Open Aids Journal','Open Journal of Preventive Medicine','Orphanet Journal of Rare Diseases','Parasites And Vectors','Peerj','Pharmacology Biochemistry and Behavior','PLoS Computational Biology',
                'Plos Genetics','Plos Genetics','Plos Neglected Tropical Diseases','PLoS One','Plos One','Plos Pathogens','Proceedings of the National Academy of Sciences of the United States of America',
                'Proceedings of the National Academy of Sciences','Proceedings of the Royal Society B: Biological Sciences','Progress in Brain Research','Progress in Neuro-Psychopharmacology & Biological Psychiatry','Protein Expression and Purification',
                'Quantitative Imaging in Medicine and Surgery','Social Cognitive and Affective Neuroscience','Stem Cells and Development','The American Journal of Clinical Nutrition','The American Journal of Pathology','The American Journal of Tropical Medicine and Hygiene',
                'The Faseb Journal','The Journal of Biological Chemistry','The Journal of Clinical Investigation','The Journal of Comparative Neurology','The Journal of Infectious Diseases','The Journal of Nutrition','Trends in Molecular Medicine','Trends in Pharmacological Sciences',
                'Western Journal of Emergency Medicine: Integrating Emergency Care with Population Health', 'PLOS Biology','Annals Of Clinical And Translational Neurology','Bmj Open Diabetes Research And Care','BONE','Elife','Immune Network','Journal Of Clinical Immunology','Journal Of Investigative Medicine High Impact Case Reports','Journal Of The American Association For Laboratory Animal Science','Molecular Therapy - Methods & Clinical Development','Online Journal Of Public Health Informatics','Public Health Action','Parasites & Vectors']

def journal_suggestion_data(journal):
    return {
        'label': '%s (%s)' %
            (journal.title, journal.publisher_romeo or
                            'unknown publisher'),
        'value': journal.title,
        'issn': journal.issn,
        'publisher': journal.publisher_romeo,
    }

def publisher_suggestion_data(publisher):
    return {
        'label': ('%s (%s)' % (publisher.name, publisher.alias))
                 if publisher.alias else
                 publisher.name,
        'value': publisher.name,
        'romeo_id': publisher.id,
        'preprint': {
                'archiving': publisher.preprint_archiving,
                'restrictions': [str(r)
                                 for r in publisher.preprint_restrictions],
            },
        'postprint': {
                'archiving': publisher.postprint_archiving,
                'restrictions': [str(r)
                                 for r in publisher.postprint_restrictions],
            },
        'pdf': {
                'archiving': publisher.pdf_archiving,
                'restrictions': [str(r)
                                 for r in publisher.pdf_restrictions],
            },
        }



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
                        if mods.journal is not None:
                            if mods.journal.title is not None:
                                try:
                                    journals = romeo.search_journal_title(mods.journal.title, type='starts') if mods.journal.title else []
                                    suggestions = [journal_suggestion_data(journal) for journal in journals]
                                    if mods.journal.title.lower() in map(str.lower, JOURNAL_LIST):
                                        mods.journal.title = suggestions[0]['value']
                                        print "JOURNAL"
                                        print mods.journal.title
                                        article.save()
                                    else:
                                        continue

                                except:
                                    suggestions = []

                            # if mods.journal.publisher is not None:
                            #     try:
                            #         publishers = romeo.search_publisher_name(mods.journal.publisher, versions='all')
                            #         suggestions = [publisher_suggestion_data(pub) for pub in publishers]
                            #         mods.journal.publisher = suggestions[0]['value']
                            #         print "PUBLISHER"
                            #         print mods.journal.publisher
                            #     except:
                            #         suggestions = []

                        else:
                            continue


                except Exception as e:
                    self.output(0, "Error processing pid: %s : %s " % (article.pid, e.message))
                    # self.counts['errors'] +=1


    def output(self, v, msg):
        '''simple function to handle logging output based on verbosity'''
        if self.verbosity >= v:
            self.stdout.write("%s\n" % msg)