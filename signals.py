import json
import logging
from datetime import datetime, timezone as dt_timezone
from django import dispatch
from django.dispatch import receiver
from django.utils import timezone
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from whatsapp import utils, settings
from whatsapp.models import Inbox, Session

logger = logging.getLogger(__name__)

webhook = dispatch.Signal()
message_sent = dispatch.Signal()
message_failed = dispatch.Signal()


def _parse_payload(request):
    """Membantu parsing request.body baik dalam bentuk dict, str, atau bytes."""
    if hasattr(request, 'body'):
        raw = request.body
        if isinstance(raw, dict):
            return raw
        elif isinstance(raw, (str, bytes)):
            try:
                return json.loads(raw)
            except Exception:
                return {}
    elif isinstance(request, dict):
        return request
    return {}


def resolve_session_id(session_key):
    """
    Resolve session_key (nomor hp atau session_id)
    ke session_id model Session di database 'WHATSAPP'.
    """
    if not session_key:
        return None
    session_key = str(session_key).strip()

    # 1. Cek langsung primary key session_id
    if Session.objects.using('WHATSAPP').filter(session_id=session_key).exists():
        return session_key

    # 2. Cek nomor telepon (membersihkan format JID jika ada)
    clean_phone = session_key.split('@')[0].split(':')[0]
    session_by_id = Session.objects.using('WHATSAPP').filter(session_id__icontains=clean_phone).first()
    if session_by_id:
        return session_by_id.session_id

    # 3. Cari berdasarkan field data['user']['id'] atau data['user']['jid']
    for s in Session.objects.using('WHATSAPP').all():
        if isinstance(s.data, dict):
            user = s.data.get('user')
            if isinstance(user, dict):
                user_id = str(user.get('id', ''))
                user_jid = str(user.get('jid', ''))
                if clean_phone and (clean_phone in user_id or clean_phone in user_jid):
                    return s.session_id

    # 4. Fallback ke session_key mentah
    return session_key


@receiver(webhook)
def on_qrcode(sender, request, **kwargs):
    try:
        body = _parse_payload(request)
        if body.get('event') == 'connection.qrcode':
            session_id = str(body.get('session') or '').strip()
            qr_data = body.get('data', {}).get('qr') or ''

            logger.info(f"✨ [QR RECEIVED] Session: {session_id} | QR: {qr_data[:20]}...")

            layer = get_channel_layer()
            async_to_sync(layer.group_send)(
                f"session.{session_id}",
                {"type": "send.data", "data": json.dumps({'qrcode': qr_data})}
            )
    except Exception as e:
        logger.error(f"Error on_qrcode: {e}")


@receiver(webhook)
def on_connection_status(sender, request, **kwargs):
    try:
        body = _parse_payload(request)
        event = body.get('event')
        if event in ('connection.open', 'connection.close'):
            session_raw = str(body.get('session') or '').strip()
            status_text = "CONNECTED" if event == 'connection.open' else "DISCONNECTED"
            logger.info(f"🌐 [STATUS] Session {session_raw} is {status_text}")

            # Update status koneksi di tabel Session jika connection.open
            if event == 'connection.open':
                resolved_sid = resolve_session_id(session_raw)
                session_obj = Session.objects.using('WHATSAPP').filter(session_id=resolved_sid).first()
                if session_obj:
                    user_data = body.get('data', {}).get('user')
                    if user_data and isinstance(session_obj.data, dict):
                        session_obj.data['user'] = user_data
                        session_obj.data['connection'] = 'open'
                        session_obj.save(using='WHATSAPP')
                        logger.info(f"🌐 [SESSION UPDATED] {resolved_sid} user data saved")
    except Exception as e:
        logger.error(f"Error on_connection_status: {e}")


@receiver(webhook)
def on_inbox(sender, request, **kwargs):
    try:
        data_json = _parse_payload(request)
        if not data_json or data_json.get('event') != 'messages.upsert':
            return

        # -----------------------------------------------------------------
        # 1. KONTRAK UTAMA (Standard Node.js Output Contract)
        # -----------------------------------------------------------------
        session_raw = str(data_json.get('session') or '').strip()
        inbox_id = data_json.get('message_id')
        message_text = data_json.get('text')
        message_type = data_json.get('message_type')
        inbox_by = data_json.get('sender')
        from_me = data_json.get('from_me')
        ts = data_json.get('timestamp')
        raw_data = data_json.get('raw') if data_json.get('raw') is not None else data_json.get('data')

        # -----------------------------------------------------------------
        # 2. DEFENSIVE FALLBACK (Jika root field kosong / payload mentah)
        # -----------------------------------------------------------------
        msg = data_json.get('raw')
        if not msg and isinstance(data_json.get('data'), dict):
            messages_list = data_json.get('data', {}).get('messages', [])
            if messages_list and isinstance(messages_list, list):
                msg = messages_list[0]
        if not isinstance(msg, dict):
            msg = {}

        msg_key = msg.get('key', {}) if isinstance(msg, dict) else {}

        # Deteksi fromMe (abaikan pesan keluar dari bot sendiri)
        if from_me is None:
            from_me = msg_key.get('fromMe', False)

        if from_me is True:
            logger.debug(f"Pesan keluar (fromMe) diabaikan: {inbox_id or msg_key.get('id')}")
            return

        # Fallback ID pesan
        if not inbox_id:
            inbox_id = msg_key.get('id')

        # Fallback isi teks pesan
        if message_text is None:
            msg_content = msg.get('message') or {}
            message_text = (
                msg_content.get('conversation') or
                msg_content.get('extendedTextMessage', {}).get('text') or
                msg_content.get('imageMessage', {}).get('caption') or
                msg_content.get('videoMessage', {}).get('caption') or
                msg_content.get('documentMessage', {}).get('caption') or
                ""
            )
        message_text = message_text or ""

        # Fallback tipe pesan
        if not message_type:
            msg_content = msg.get('message') or {}
            message_type = next(iter(msg_content.keys()), 'conversation') if msg_content else 'conversation'
        message_type = message_type or 'conversation'

        # Fallback pengirim pesan (prioritaskan nomor HP jika sender adalah @lid)
        sender_pn = msg_key.get('senderPn') or msg_key.get('remoteJidAlt')
        if not inbox_by or '@lid' in str(inbox_by):
            if sender_pn:
                inbox_by = sender_pn
            elif not inbox_by:
                inbox_by = (
                    msg_key.get('remoteJid') or
                    data_json.get('metadata', {}).get('sender') or
                    ''
                )

        # Fallback timestamp
        if not ts:
            ts = msg.get('messageTimestamp')

        if ts:
            try:
                ts_float = float(ts)
                if ts_float > 1e11:
                    ts_float = ts_float / 1000
                inbox_date = datetime.fromtimestamp(ts_float, tz=dt_timezone.utc)
            except Exception:
                inbox_date = timezone.now()
        else:
            inbox_date = timezone.now()

        # Raw payload
        if not isinstance(raw_data, dict):
            raw_data = msg if isinstance(msg, dict) and msg else {'payload': raw_data}

        # Resolve session_id ke model Session di database 'WHATSAPP'
        resolved_session_id = resolve_session_id(session_raw)

        # Simpan atau update record ke tabel Inbox menggunakan koneksi database 'WHATSAPP'
        inbox_defaults = {
            'message': message_text,
            'message_type': message_type,
            'inbox_by': inbox_by,
            'inbox_date': inbox_date,
            'data': raw_data,
            'session_id': resolved_session_id,
            'status': 'draft',
        }

        if inbox_id:
            inbox = Inbox.objects.using('WHATSAPP').filter(inbox_id=inbox_id).first()
            if inbox:
                for attr, val in inbox_defaults.items():
                    setattr(inbox, attr, val)
                inbox.save(using='WHATSAPP')
                logger.info(f"📥 [INBOX UPDATED] ID: {inbox_id} | Dari: {inbox_by} | Sesi: {resolved_session_id}")
            else:
                inbox = Inbox.objects.using('WHATSAPP').create(
                    inbox_id=inbox_id,
                    is_processed=False,
                    **inbox_defaults
                )
                logger.info(f"📥 [INBOX INSERTED] ID: {inbox_id} | Dari: {inbox_by} | Sesi: {resolved_session_id}")
        else:
            inbox = Inbox.objects.using('WHATSAPP').create(
                is_processed=False,
                **inbox_defaults
            )
            logger.info(f"📥 [INBOX INSERTED] ID: {inbox.inbox_id} | Dari: {inbox_by} | Sesi: {resolved_session_id}")

        # Realtime broadcast via Channel Layers ke grup session
        push_name = data_json.get('push_name') or msg.get('pushName') or "Unknown"
        logger.info(f"🚀 Memancarkan ke grup: session.{session_raw} & session.{resolved_session_id} | Dari: {push_name}")

        layer = get_channel_layer()
        broadcast_payload = {
            "type": "new_message",
            "content": {
                "inbox_id": getattr(inbox, 'inbox_id', inbox_id),
                "push_name": push_name,
                "inbox_by": inbox_by,
                "text": message_text,
                "session_id": resolved_session_id,
                "created": inbox.created.isoformat() if hasattr(inbox, 'created') and inbox.created else None,
            }
        }

        groups_to_notify = set(filter(None, [session_raw, resolved_session_id]))
        for target_group in groups_to_notify:
            async_to_sync(layer.group_send)(
                f"session.{target_group}",
                {
                    "type": "send.data",
                    "data": json.dumps(broadcast_payload)
                }
            )

    except Exception as e:
        logger.error(f"❌ Error Signal on_inbox: {e}", exc_info=True)


@receiver(message_sent)
def on_message_sent(sender, instance=None, outbox=None, **kwargs):
    """
    Handler saat pesan WhatsApp berhasil terkirim (Skenario 1).
    Memancarkan event realtime ke WebSocket Channel Layer untuk update UI & client.
    """
    try:
        layer = get_channel_layer()
        if not layer:
            return

        session_id = getattr(instance, 'session_id', None) or (outbox.session_id if outbox else '')
        sent_for = getattr(instance, 'sent_for', '')
        msg_id = getattr(instance, 'sent_id', instance.pk if hasattr(instance, 'pk') else '')
        sent_date = getattr(instance, 'sent_date', timezone.now())
        
        broadcast_payload = {
            "type": "message_sent",
            "event": "message.sent",
            "content": {
                "sent_id": str(msg_id),
                "outbox_id": getattr(outbox, 'pk', None) or getattr(instance, 'properties', {}).get('outbox'),
                "sent_for": str(sent_for),
                "message": getattr(instance, 'message', ''),
                "message_type": getattr(instance, 'message_type', 'conversation'),
                "session_id": str(session_id),
                "sent_date": sent_date.isoformat() if hasattr(sent_date, 'isoformat') else str(sent_date),
                "status": "sent",
            }
        }

        # 1. Broadcast ke grup session.{session_id} (untuk WebSocket client yang mendengarkan sesi ini)
        groups = set(filter(None, [session_id]))
        if outbox and getattr(outbox, 'session', None):
            if getattr(outbox.session, 'session_name', None):
                groups.add(outbox.session.session_name)
        
        for grp in groups:
            async_to_sync(layer.group_send)(
                f"session.{grp}",
                {
                    "type": "send.data",
                    "data": json.dumps(broadcast_payload)
                }
            )

        # 2. Broadcast ke grup umum whatsapp_webhooks
        async_to_sync(layer.group_send)(
            "whatsapp_webhooks",
            {
                "type": "send.data",
                "data": json.dumps(broadcast_payload)
            }
        )
        
        logger.info(f"📡 [WS BROADCAST] Event message.sent dipancarkan untuk ID: {msg_id} ke {groups | {'whatsapp_webhooks'}}")
    except Exception as e:
        logger.error(f"❌ Error on_message_sent signal broadcast: {e}", exc_info=True)


@receiver(message_failed)
def on_message_failed(sender, instance=None, error=None, **kwargs):
    """
    Handler saat pesan WhatsApp gagal terkirim.
    Memancarkan event error realtime ke WebSocket Channel Layer.
    """
    try:
        layer = get_channel_layer()
        if not layer:
            return

        session_id = getattr(instance, 'session_id', '')
        outbox_for = getattr(instance, 'outbox_for', '')
        outbox_id = getattr(instance, 'pk', '')
        retry = getattr(instance, 'retry', 0)

        broadcast_payload = {
            "type": "message_failed",
            "event": "message.failed",
            "content": {
                "outbox_id": str(outbox_id),
                "outbox_for": str(outbox_for),
                "session_id": str(session_id),
                "retry": retry,
                "error": error or getattr(instance, 'data', {}).get('error'),
                "status": "failed",
            }
        }

        groups = set(filter(None, [session_id]))
        for grp in groups:
            async_to_sync(layer.group_send)(
                f"session.{grp}",
                {
                    "type": "send.data",
                    "data": json.dumps(broadcast_payload)
                }
            )

        async_to_sync(layer.group_send)(
            "whatsapp_webhooks",
            {
                "type": "send.data",
                "data": json.dumps(broadcast_payload)
            }
        )
        logger.warning(f"📡 [WS BROADCAST] Event message.failed dipancarkan untuk Outbox ID: {outbox_id}")
    except Exception as e:
        logger.error(f"❌ Error on_message_failed signal broadcast: {e}", exc_info=True)

