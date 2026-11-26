import logging

from django.urls import re_path

from whatsapp import consumers

logger = logging.getLogger(__name__)

websocket_urlpatterns = [
    re_path(fr'^ws/whatsapp/webhook/$', consumers.WebhookConsumer.as_asgi()),
    re_path(r'^ws/whatsapp/(?P<pk>\d+)/$', consumers.SessionConsumer.as_asgi()),
]
