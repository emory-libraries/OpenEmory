import os
import shutil
from fabric.api import env, lcd, local, prefix

# omit these from the test coverage report
env.omit_coverage = ','.join([
    os.environ['VIRTUAL_ENV'],
    'openemory/manage.py',
    'openemory/settings.py',
    'openemory/localsettings.py',
    ])

def all_deps():
    '''Locally install all dependencies.'''
    local('pip install -r pip-install-req.txt -r pip-dev-req.txt')

def test():
    '''Locally run all tests.'''
    if os.path.exists('test-results'):
        shutil.rmtree('test-results')

    local('coverage run --branch openemory/manage.py test --noinput')
    local('coverage xml --omit=%(omit_coverage)s' % env)

def doc():
    '''Locally build documentation.'''
    with lcd('doc'):
        local('make clean html')

def build():
    '''Run a full local build/test cycle.'''
    all_deps()
    test()
    doc()
