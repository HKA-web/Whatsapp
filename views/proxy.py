import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.sites.models import Site

from library.revproxy.views import ProxyView
from whatsapp import settings

logger = logging.getLogger(__name__)


def headers(token: str, ):
    return {
        'Content-Type': 'application/json',
        'Authorization': f'''Bearer {token}'''
    }


class WhatsAppProxyView(ProxyView, LoginRequiredMixin, ):
    def __init__(self, *args, **kwargs):
        self.add_remote_user = True
        self.add_x_forwarded = True
        self.upstream = f'''http://{Site.objects.get_current().domain}:{settings.PORT}/api'''
        super().__init__(*args, **kwargs)
