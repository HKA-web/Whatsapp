import json
import logging

from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer
from prodict import Prodict

from whatsapp import signals

logger = logging.getLogger(__name__)


class WebhookConsumer(JsonWebsocketConsumer):
    def connect(self):
        # Ambil session_id dari URL jika ada, atau gunakan grup umum
        self.group_name = "whatsapp_webhooks"
        async_to_sync(self.channel_layer.group_add)(
            self.group_name,
            self.channel_name
        )
        self.accept()
        logger.info("✅ Websocket Connected")

    def receive_json(self, content):
        logger.info(f"📩 Data masuk: {content.get('event')}")
        signals.webhook.send(
            sender=self.__class__.__name__,
            request=Prodict(body=json.dumps(content))
        )

    def send_data(self, event):
        self.send(text_data=event["data"])