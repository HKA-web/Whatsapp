import logging

from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)


# whatsapp/consumers.py
class SessionConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Ambil nomor HP dari URL (ws/whatsapp/6285648007953/)
        self.pk = self.scope['url_route']['kwargs']['pk']
        self.group_name = f"session.{self.pk}"

        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()

    # Method ini HARUS ADA dan namanya harus 'send_data'
    # karena di signals.py Anda mengirim {"type": "send.data", ...}
    async def send_data(self, event):
        await self.send(text_data=event["data"])