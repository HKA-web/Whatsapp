import logging
import json
import requests
from datetime import datetime
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from core.fields import ShortUUIDField, StatusField
from core.models import Base
from whatsapp import settings
from django.dispatch import receiver
from django.db.models import signals
from prodict import Prodict
from http import HTTPStatus
from django.utils.timezone import make_aware
from core.utils import ShortUUID
from django.conf import settings as djangosettings

logger = logging.getLogger(__name__)

class Outbox(Base, ):
    outbox_id = ShortUUIDField(
        length=25,
        max_length=100,
        primary_key=True,
        verbose_name=_('outbox id'),
        help_text=_('Used for identity'),
    )
    sent_id = ShortUUIDField(
        length=25,
        max_length=100,
        verbose_name=_('sent id'),
        help_text=_('Used for identity to uses when message is sent'),
    )
    template_id = models.CharField(
        blank=True,
        null=True,
        verbose_name=_('template'),
        help_text=_('Used for linked key'),
    )
    message = models.TextField(
        blank=True,
        null=True,
        verbose_name=_('message'),
        help_text=_('Used for content'),
    )
    message_type = models.CharField(
        verbose_name=_('message type'),
        help_text=_('Used for detect type'),
    )
    outbox_for = models.CharField(
        verbose_name=_('outbox for'),
        help_text=_('Used for tracking outbox for'),
    )
    prepare_date = models.DateTimeField(
        default=timezone.now,
        verbose_name=_('prepare date'),
        help_text=_('Used for tracking begin outbox prepared'),
    )
    retry = models.IntegerField(
        default=0,
        verbose_name=_('retry'),
        help_text=_('Used for retry send outbox'),
    )
    scheduled = models.BooleanField(
        default=False,
        verbose_name=_('scheduled'),
        help_text=_('Used for scheduled message'),
    )
    scheduled_date = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=_('scheduled date'),
        help_text=_('Used for scheduled message send date'),
    )
    is_interactive = models.BooleanField(
        default=False,
        verbose_name=_('is interactive'),
        help_text=_('Used for message is required answer'),
    )
    is_answered = models.BooleanField(
        default=False,
        verbose_name=_('is answered'),
        help_text=_('Used for message is answered'),
    )
    answered_date = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=_('answered date'),
        help_text=_('Used for message answered date'),
    )
    data = models.JSONField(
        default=dict,
        verbose_name=_('data'),
        help_text=_('Used for data value'),
    )
    session_id = models.CharField(
        verbose_name=_('session'),
        help_text=_('Used for linked key'),
    )
    status = StatusField(transition=False, )

    class Meta:
        managed = False
        db_table = u'\"{}\".\"outbox\"'.format(settings.SCHEMA)
        verbose_name = _('Outbox')
        permissions = []

    @property
    def session(self):
        if self.session_id:
            from whatsapp.models import Session
            return Session.objects.using('WHATSAPP').filter(pk=self.session_id).first()
        return None

    @property
    def template(self):
        if getattr(self, 'template_id', None):
            from whatsapp.models import Template
            return Template.objects.using('WHATSAPP').filter(pk=self.template_id).first()
        return None
    
    def render(self, ):
        if self.template and self.template.session not in (self.session,):
            from whatsapp.models import Template
            raise Template.DoesNotExist('Template matching query does not exist', )
        if self.template and not self.message:
            from django.template import Template, Context
            setattr(self, 'message', Template(self.template.template, ).render(Context(dict(self.data, **self.properties, ))))

    def send(self, once=False, ):
        from whatsapp.models import Sent
        self.refresh_from_db(using='WHATSAPP')

        # 1. Ekstrak pesan teks dari self.message
        text_content = self.message or ''
        try:
            parsed = json.loads(self.message)
            if isinstance(parsed, dict):
                text_content = parsed.get('text') or parsed.get('message') or parsed.get('body') or self.message
            elif isinstance(parsed, list) and len(parsed) > 0 and isinstance(parsed[0], dict):
                text_content = parsed[0].get('text') or parsed[0].get('message') or self.message
        except Exception:
            text_content = self.message or ''

        # Tambahkan refid acak jika belum ada
        if text_content and '__ref:' not in text_content:
            ref = ShortUUID().random(length=5)
            text_content = f"{text_content}\n\n__ref:{ref}__"
            self.message = text_content

        # 2. Tentukan nama/nomor sesi WhatsApp
        session_name = None
        if self.session:
            if isinstance(self.session.data, dict) and 'user' in self.session.data:
                user_id = str(self.session.data['user'].get('id', ''))
                if user_id:
                    session_name = user_id.split('@')[0].split(':')[0]
            if not session_name and self.session.session_name:
                session_name = self.session.session_name
            if not session_name:
                session_name = self.session.session_id
        else:
            session_name = self.session_id

        # 3. Bentuk target URL dan Payload REST API (WAHA Style)
        whatsapp_config = getattr(settings, 'WHATSAPP', {})
        port = whatsapp_config.get('PORT', 3002) if isinstance(whatsapp_config, dict) else getattr(settings, 'WHATSAPP_PORT', 3002)
        base_url = f"http://127.0.0.1:{port}"

        target_chat = self.outbox_for
        if '@lid' in str(target_chat):
            from whatsapp.models import Inbox
            inbox_match = Inbox.objects.using('WHATSAPP').filter(inbox_by=target_chat).order_by('-created').first()
            if inbox_match and isinstance(inbox_match.data, dict):
                pn = inbox_match.data.get('key', {}).get('senderPn')
                if pn:
                    target_chat = pn

        # Cek simulasi mengetik (default: False, hanya aktif jika eksplisit diminta)
        sim_typing = False
        if isinstance(self.properties, dict) and 'simulateTyping' in self.properties:
            sim_typing = bool(self.properties['simulateTyping'])
        elif isinstance(self.data, dict) and 'simulateTyping' in self.data:
            sim_typing = bool(self.data['simulateTyping'])

        payload = {
            'session': session_name,
            'chatId': target_chat,
            'simulateTyping': sim_typing,
        }

        if isinstance(self.properties, dict) and 'typingDelay' in self.properties:
            payload['typingDelay'] = self.properties['typingDelay']
        elif isinstance(self.data, dict) and 'typingDelay' in self.data:
            payload['typingDelay'] = self.data['typingDelay']

        # Cek jika ada referensi pesan yang di-reply / di-quote
        reply_to = None
        if isinstance(self.properties, dict):
            reply_to = self.properties.get('reply_to') or self.properties.get('inbox')
        if not reply_to and isinstance(self.data, dict):
            reply_to = self.data.get('reply_to') or self.data.get('messageId')
        if reply_to:
            payload['reply_to'] = str(reply_to)

        if isinstance(self.data, dict) and self.data.get('quoted'):
            payload['quoted'] = self.data.get('quoted')

        endpoint = f"{base_url}/api/sendText"
        if self.message_type in ('image',):
            endpoint = f"{base_url}/api/sendImage"
            file_url = self.data.get('url', '') if isinstance(self.data, dict) else ''
            payload['file'] = {'url': file_url}
            payload['caption'] = text_content
        elif self.message_type in ('file', 'document'):
            endpoint = f"{base_url}/api/sendFile"
            file_url = self.data.get('url', '') if isinstance(self.data, dict) else ''
            payload['file'] = {
                'url': file_url,
                'filename': self.data.get('filename', 'document') if isinstance(self.data, dict) else 'document'
            }
            payload['caption'] = text_content
        else:
            payload['text'] = text_content

        try:
            logger.info(f"📤 [OUTBOX SEND] Mengirim ke {endpoint} untuk {self.outbox_for} (Sesi: {session_name})")
            response = requests.post(endpoint, json=payload, timeout=30)

            if response.status_code in (HTTPStatus.OK, HTTPStatus.CREATED):
                resp_data = response.json()
                results = resp_data.get('results', [resp_data])
                for res in results:
                    if res.get('success'):
                        msg_id = res.get('id') or self.sent_id or ShortUUID().random(length=25)
                        sent_to = res.get('to') or self.outbox_for
                        ts = res.get('timestamp')
                        sent_date = timezone.now()
                        if ts:
                            try:
                                ts_val = ts.get('low') if isinstance(ts, dict) else ts
                                sent_date = make_aware(datetime.fromtimestamp(int(ts_val)))
                            except Exception:
                                sent_date = timezone.now()

                        value = dict(
                            template_id=self.template_id if hasattr(self, 'template_id') else None,
                            message=text_content,
                            message_type=self.message_type or 'conversation',
                            sent_for=sent_to,
                            sent_date=sent_date,
                            prepare_date=self.prepare_date or timezone.now(),
                            retry=self.retry,
                            scheduled=self.scheduled,
                            scheduled_date=self.scheduled_date,
                            is_interactive=self.is_interactive,
                            is_answered=self.is_answered,
                            answered_date=self.answered_date,
                            session_id=self.session_id,
                            data=res,
                            properties=self.properties or {},
                        )
                        if 'outbox' not in value['properties']:
                            value['properties']['outbox'] = self.pk

                        sent, created = Sent.objects.using('WHATSAPP').get_or_create(
                            pk=msg_id,
                            defaults=value,
                        )
                        if created:
                            logger.info(f"✅ [SENT CREATED] ID: {msg_id} untuk {sent_to}")

                        # Trigger Signal & WebSocket Broadcast (Skenario 1)
                        try:
                            from whatsapp import signals as whatsapp_signals
                            whatsapp_signals.message_sent.send(
                                sender=self.__class__,
                                instance=sent,
                                outbox=self,
                                result=res,
                            )
                        except Exception as sig_err:
                            logger.error(f"Error triggering message_sent signal: {sig_err}")

                # Outbox selesai diproses dan dipindahkan ke Sent
                logger.info(f"🗑️ [OUTBOX DELETED] Outbox {self.pk} berhasil terkirim dan dihapus dari antrean.")
                self.delete(using='WHATSAPP',soft=False, )
            else:
                try:
                    err_json = response.json()
                except Exception:
                    err_json = {'status_code': response.status_code, 'text': response.text}
                logger.error(f"❌ [OUTBOX FAILED] HTTP {response.status_code}: {err_json}")
                if not isinstance(self.data, dict):
                    self.data = {}
                self.data.update(error=err_json)
                self.save(using='WHATSAPP', update_fields=['data'])

                # Trigger Signal Error & WebSocket Broadcast (Skenario 1)
                try:
                    from whatsapp import signals as whatsapp_signals
                    whatsapp_signals.message_failed.send(
                        sender=self.__class__,
                        instance=self,
                        error=err_json,
                    )
                except Exception as sig_err:
                    logger.error(f"Error triggering message_failed signal: {sig_err}")

        except Exception as e:
            logger.error(f"❌ [OUTBOX EXCEPTION] Gagal mengirim outbox {self.pk}: {e}", exc_info=True)
            if not isinstance(self.data, dict):
                self.data = {}
            self.data.update(error=str(e))
            self.save(using='WHATSAPP', update_fields=['data'])

            # Trigger Signal Error & WebSocket Broadcast (Skenario 1)
            try:
                from whatsapp import signals as whatsapp_signals
                whatsapp_signals.message_failed.send(
                    sender=self.__class__,
                    instance=self,
                    error=str(e),
                )
            except Exception as sig_err:
                logger.error(f"Error triggering message_failed signal: {sig_err}")


        return self


@receiver(signals.pre_save, sender=Outbox, )
def on_outbox_create(sender, instance: Outbox, **kwargs, ):
    if instance:
        if instance._state.adding:
            instance.render()
            if instance.message and '__ref:' not in str(instance.message):
                ref = ShortUUID().random(length=5)
                instance.message = f"{instance.message}\n\n__ref:{ref}__"


@receiver(signals.post_save, sender=Outbox, )
def on_outbox_created(sender, instance: Outbox, created, **kwargs, ):
    if instance and created:
        if not instance.scheduled:
            try:
                from whatsapp.tasks import process_outbox as process
                process(instance)
            except Exception as e:
                logger.warning(f"Huey enqueue error ({e}), processing outbox directly.")
                instance.send()
