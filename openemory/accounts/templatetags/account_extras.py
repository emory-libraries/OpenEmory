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
