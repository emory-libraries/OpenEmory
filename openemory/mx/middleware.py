from django.conf import settings
from django.shortcuts import render
from downtime.middleware import DowntimeMiddleware


class DownpageMiddleware(DowntimeMiddleware):

    def process_request(self, request):
        downtime_request=super(DownpageMiddleware, self).process_request(request)
        allowed_ips = getattr(settings, 'DOWNTIME_ALLOWED_IPS', [])
        if downtime_request and allowed_ips and self.client_ip(request) in allowed_ips:
            return None
        else:
            return downtime_request

    @classmethod
    def client_ip(self, request):
        """
        Returns the client IP address from the request.
        """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
