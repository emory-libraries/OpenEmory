# file openemory/accounts/templatetags/account_extras.py
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

from django import template
from django.contrib.auth.models import User

register = template.Library()

@register.tag
def user_for_netid(parser, token):
    try:
        tag_name, netid_var, _as, target_var = token.contents.split()
        if _as != 'as':
            raise ValueError()
    except ValueError:
        raise template.TemplateSyntaxError('%r tag invalid arguments' %
                (token.contents.split()[0],))
    
    return UserForNetidNode(netid_var, target_var)


class UserForNetidNode(template.Node):
    def __init__(self, netid_var, target_var):
        self.netid_var = template.Variable(netid_var)
        self.target_var = target_var

    def render(self, context):
        try:
            netid = self.netid_var.resolve(context)
            if netid:
                user = User.objects.get(username=netid)
            else:
                user = None
        except (template.VariableDoesNotExist, User.DoesNotExist):
            user = None
        context[self.target_var] = user
        return ''
