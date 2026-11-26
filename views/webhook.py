import json
import logging
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from whatsapp import signals

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class WebhookView(View):
    """
    HTTP Webhook Endpoint sebagai Fallback cadangan resmi.
    Menerima payload event dari WhatsApp Engine (Node.js) via HTTP POST
    dan meneruskannya ke signals.webhook (sama seperti WebhookConsumer pada WebSocket).
    """

    def get(self, request, *args, **kwargs):
        return JsonResponse({
            'status': 'ok',
            'service': 'WhatsApp HTTP Webhook Fallback',
            'method': 'POST',
        }, status=200)

    def post(self, request, *args, **kwargs):
        try:
            event_name = 'unknown'
            if request.body:
                try:
                    payload = json.loads(request.body)
                    if isinstance(payload, dict):
                        event_name = payload.get('event', 'unknown')
                except Exception:
                    pass

            logger.info(f"📩 [HTTP WEBHOOK] Event diterima via HTTP POST: {event_name}")

            signals.webhook.send(
                sender=self.__class__.__name__,
                request=request
            )

            return JsonResponse({
                'status': 'success',
                'event': event_name,
                'message': 'Webhook processed successfully'
            }, status=200)
        except Exception as e:
            logger.error(f"❌ [HTTP WEBHOOK ERROR] Gagal memproses webhook HTTP: {e}", exc_info=True)
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)
