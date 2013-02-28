# file doc/docsettings.py
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

from openemory.settings import *
# Sphinx loads things in wonky order sometimes. Normally this shouldn't
# matter, but when it loads eullocal, tracking, and django admin all
# together, a mutual dependency appears between the
# eullocal.django.emory_ldap profile creation signal, tracking's urls
# self-check, and django admin's autodiscover. This dependency doesn't
# appear to happen when django loads things itself. It's pretty wacky. If we
# disable AUTH_PROFILE_MODULE just for docs, though, then emory_ldap doesn't
# create its signal, and the mutual dependency goes away.
AUTH_PROFILE_MODULE = None
