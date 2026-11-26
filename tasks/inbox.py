import json
import logging
import os
import platform
import re as regex
from collections import namedtuple
from datetime import datetime

import psutil
from django.conf import settings as djangosettings
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

import library.djangohuey as huey
from core.utils import ShortUUID
from whatsapp.apps import ApplicationConfig
from whatsapp.models import Inbox, Outbox, Command, CommandActive

logger = logging.getLogger(__name__)


def prepare(inbox: Inbox):
    """
    Mencocokkan pesan masuk (inbox) dengan Command yang tersedia di tabel whatsapp.command,
    atau melanjutkan alur percakapan bertingkat dari CommandActive sebelumnya.
    """
    command_active = None

    def check(cmd_text: str):
        if not cmd_text:
            return None
        # 1. Cari exact match (sesi yang sama atau global session)
        searchs = Command.objects.using('WHATSAPP').filter(
            Q(session_id=inbox.session_id) | Q(session_id__isnull=True) | Q(session_id=''),
            command__iexact=cmd_text,
            enable=True,
        )
        # 2. Cari dengan format slash (contoh: 'cek poin' -> 'cek/poin')
        if not searchs.exists():
            searchs = Command.objects.using('WHATSAPP').filter(
                Q(session_id=inbox.session_id) | Q(session_id__isnull=True) | Q(session_id=''),
                command__iexact='/'.join(cmd_text.split()),
                enable=True,
            )
        if searchs.exists():
            return searchs
        
        # 3. Rekursi dengan longest prefix (contoh: 'cek poin 12345' -> coba 'cek poin')
        parts = cmd_text.split()
        if len(parts) > 1:
            next_prefix = ' '.join(parts[:-1])
            return check(next_prefix.strip())
        return None

    cmd_raw = inbox.command.strip() if inbox.command else ''
    clean_words = ' '.join([w for w in regex.split(r'\W+', cmd_raw) if w]) if cmd_raw else ''
    commands = check(clean_words) if clean_words else None

    if commands and commands.exists():
        for cmd in commands:
            # Ekstraksi parameter positional jika ada sisa kata setelah nama command
            cmd_clean_raw = regex.sub(r'^[^\w]+', '', cmd_raw).strip()
            cmd_words = cmd_clean_raw.split()
            matched_words = cmd.command.strip().split()
            matched_count = len(matched_words)

            if len(cmd_words) > matched_count:
                trailing_params = cmd_words[matched_count:]
                formatted_params = list(trailing_params)
                req_params = cmd.required_parameter or []
                for idx, req_item in enumerate(req_params):
                    if idx < len(formatted_params):
                        formatted_params[idx] = f"{req_item}={formatted_params[idx]}"
                inbox.message = f"{cmd.command.strip().lower()}\n" + '\n'.join(formatted_params)
                if inbox.pk and not inbox._state.adding:
                    inbox.save(using='WHATSAPP', update_fields=['message'])

            command_active = CommandActive.objects.using('WHATSAPP').create(
                command=cmd,
                command_by=inbox.inbox_by,
                parameter=inbox.parameter,
                enable=True,
            )
            break
    else:
        # Jika bukan command langsung, periksa apakah user memiliki sesi aktif sebelumnya di CommandActive
        actives = CommandActive.objects.using('WHATSAPP').filter(
            command_by=inbox.inbox_by,
            enable=True,
        )
        if inbox.session_id:
            actives = actives.filter(Q(command__session_id=inbox.session_id) | Q(command__session_id__isnull=True))

        for active in actives:
            chained_name = f"{active.command.command}/{cmd_raw}".strip()
            chained_clean = ' '.join(regex.split(r'\W+', chained_name))
            commands = check(chained_clean)
            if commands and commands.exists():
                for cmd in commands:
                    command_active = CommandActive.objects.using('WHATSAPP').create(
                        command=cmd,
                        command_by=inbox.inbox_by,
                        parameter=inbox.parameter,
                        enable=True,
                    )
                    break
            if command_active:
                break

    # Pengecekan parameter wajib (required_parameter)
    if command_active:
        target_cmd = command_active.command.mirror if command_active.command.mirror else command_active.command
        req_params = target_cmd.required_parameter or []
        chk_param = target_cmd.check_parameter

        if chk_param and req_params:
            missing = [p for p in req_params if p not in (command_active.parameter or {})]
            if missing:
                missing_str = '\n'.join(missing)
                ref = ShortUUID().random(length=5)
                Outbox.objects.using('WHATSAPP').create(
                    message=f"Parameter \n{missing_str} \nIs Required\n\n__ref:{ref}__",
                    message_type='conversation',
                    outbox_for=inbox.inbox_by,
                    session_id=inbox.session_id,
                    properties=dict(command=target_cmd.pk, inbox=inbox.inbox_id, reply_to=inbox.inbox_id),
                    data=dict(reply_to=inbox.inbox_id, quoted=inbox.data),
                )
                return None

    return command_active


def _mark_processed(inbox: Inbox):
    inbox.is_processed = True
    try:
        if inbox.pk and not inbox._state.adding:
            inbox.save(using='WHATSAPP', update_fields=['is_processed'])
        else:
            inbox.save(using='WHATSAPP')
    except Exception as save_err:
        logger.debug(f"Could not update is_processed on inbox: {save_err}")


def _has_media_keys(msg):
    """
    Memeriksa apakah objek pesan memiliki kunci dekripsi media (url / directPath dan mediaKey).
    """
    if not isinstance(msg, dict):
        return False
    for k in ('imageMessage', 'videoMessage', 'audioMessage', 'documentMessage', 'stickerMessage'):
        if k in msg and isinstance(msg[k], dict):
            media = msg[k]
            if (media.get('url') or media.get('directPath')) and media.get('mediaKey'):
                return True
    for vo in ('viewOnceMessage', 'viewOnceMessageV2', 'viewOnceMessageV2Extension', 'ephemeralMessage', 'documentWithCaptionMessage'):
        if vo in msg and isinstance(msg[vo], dict):
            inner = msg[vo].get('message', {})
            if _has_media_keys(inner):
                return True
    return False


def _handle_rvo_command(inbox: Inbox):
    """
    Handler untuk command .rvo / rvo / buka / lihat:
    Membuka dan mengirimkan kembali media sekali lihat (View Once) yang di-quote atau terakhir diterima di chat.
    """
    try:
        raw_msg = inbox.data or {}
        context_info = None

        if isinstance(raw_msg, dict):
            context_info = (
                raw_msg.get('message', {}).get('extendedTextMessage', {}).get('contextInfo')
                or raw_msg.get('raw', {}).get('message', {}).get('extendedTextMessage', {}).get('contextInfo')
                or raw_msg.get('payload', {}).get('raw', {}).get('message', {}).get('extendedTextMessage', {}).get('contextInfo')
            )
            if not context_info and isinstance(raw_msg.get('data'), dict):
                first_msg = raw_msg['data'].get('messages', [{}])[0]
                if isinstance(first_msg, dict):
                    context_info = first_msg.get('message', {}).get('extendedTextMessage', {}).get('contextInfo')

        quoted_message = context_info.get('quotedMessage') if isinstance(context_info, dict) else None
        quoted_id = context_info.get('stanzaId') if isinstance(context_info, dict) else None

        orig_message = None
        target_id = quoted_id

        # 1. Coba cari pesan yang di-quote di Inbox Django berdasarkan target_id
        if target_id:
            clean_id = str(target_id).split('-')[0]
            candidate_qs = Inbox.objects.using('WHATSAPP').filter(
                Q(inbox_id=target_id) | Q(inbox_id=f"{target_id}-1") | Q(inbox_id__startswith=clean_id)
            )
            for cached_ib in candidate_qs[:5]:
                if cached_ib and cached_ib.data:
                    raw_d = cached_ib.data
                    candidate = (
                        raw_d.get('message')
                        or raw_d.get('raw', {}).get('message')
                        or raw_d.get('payload', {}).get('raw', {}).get('message')
                    )
                    if _has_media_keys(candidate):
                        orig_message = candidate
                        target_id = cached_ib.inbox_id
                        logger.info(f"🎯 [RVO DIRECT MATCH] Ditemukan pesan media di Inbox ID: {target_id}")
                        break

        # 2. Jika tidak ditemukan atau tidak memiliki mediaKey (misal perbedaan stanzaId client WhatsApp),
        # cari pesan media terakhir di chat ini yang dikirim ke bot / grup
        if not orig_message or not _has_media_keys(orig_message):
            candidate_senders = {inbox.inbox_by}
            participant = context_info.get('participant') if isinstance(context_info, dict) else None
            if participant:
                candidate_senders.add(participant)

            lid_candidates = [
                os.path.join(str(djangosettings.BASE_DIR), 'whatsapp', 'engine', 'baileys', 'sessions', 'lid_map.json'),
                os.path.join(str(djangosettings.BASE_DIR), 'whatsapp', 'engine', 'whatsmeow', 'sessions', 'lid_map.json'),
                os.path.join(str(djangosettings.BASE_DIR), 'whatsapp', 'engine', 'sessions', 'lid_map.json'),
            ]
            # Ambil pemetaan nomor alternatif (LID <-> Phone) jika ada
            for lid_file in lid_candidates:
                try:
                    if os.path.exists(lid_file):
                        with open(lid_file, 'r', encoding='utf-8') as lf:
                            lmap = json.load(lf)
                            if inbox.inbox_by in lmap:
                                candidate_senders.add(lmap[inbox.inbox_by])
                            if participant and participant in lmap:
                                candidate_senders.add(lmap[participant])
                except Exception:
                    pass

            is_group = '@g.us' in str(inbox.inbox_by)
            fallback_query = (
                Inbox.objects.using('WHATSAPP')
                .filter(session_id=inbox.session_id)
                .exclude(inbox_id=inbox.inbox_id)
            )

            if is_group:
                fallback_query = fallback_query.filter(inbox_by=inbox.inbox_by)
            else:
                fallback_query = fallback_query.filter(inbox_by__in=candidate_senders)

            # Cek 50 pesan terakhir di percakapan tersebut yang memiliki kunci media
            for fallback_ib in fallback_query.order_by('-created')[:50]:
                if fallback_ib and fallback_ib.data:
                    raw_d = fallback_ib.data
                    candidate = (
                        raw_d.get('message')
                        or raw_d.get('raw', {}).get('message')
                        or raw_d.get('payload', {}).get('raw', {}).get('message')
                    )
                    if _has_media_keys(candidate):
                        orig_message = candidate
                        target_id = fallback_ib.inbox_id
                        logger.info(f"🔄 [RVO FALLBACK] Menggunakan pesan media terakhir di chat (ID: {target_id}) untuk {inbox.inbox_by}")
                        break

        if not orig_message and not quoted_message and not target_id:
            ref = ShortUUID().random(length=5)
            reply = (
                "⚠️ *Cara Membuka Pesan Sekali Lihat:*\n\n"
                "Balas *(Reply / Quote)* foto atau video sekali lihat tersebut, "
                "lalu ketik perintah *.rvo* atau *buka*.\n\n"
                f"__ref:{ref}__"
            )
            Outbox.objects.using('WHATSAPP').create(
                message=reply,
                message_type='conversation',
                outbox_for=inbox.inbox_by,
                session_id=inbox.session_id,
                properties=dict(inbox=inbox.inbox_id, reply_to=inbox.inbox_id),
                data=dict(reply_to=inbox.inbox_id, quoted=inbox.data),
            )
            _mark_processed(inbox)
            logger.info(f"ℹ️ [RVO COMMAND] Hint dikirim ke {inbox.inbox_by} karena tidak ada media ditemukan.")
            return

        target_message = orig_message or quoted_message

        whatsapp_config = getattr(djangosettings, 'WHATSAPP', {})
        port = whatsapp_config.get('PORT', 3002) if isinstance(whatsapp_config, dict) else getattr(djangosettings, 'WHATSAPP_PORT', 3002)
        download_url = f"http://127.0.0.1:{port}/api/downloadMedia"

        import requests
        req_payload = {
            'session': inbox.session_id,
            'chatId': inbox.inbox_by,
            'message': {
                'key': {
                    'id': target_id or 'dummy_id',
                    'remoteJid': inbox.inbox_by,
                    'participant': context_info.get('participant') if isinstance(context_info, dict) else None,
                },
                'message': target_message,
            },
            'messageId': target_id,
        }

        logger.info(f"🔓 [RVO COMMAND] Mengunduh media untuk {inbox.inbox_by} (ID: {target_id})...")
        resp = requests.post(download_url, json=req_payload, timeout=25)

        if resp.status_code == 200 and resp.json().get('success'):
            media_result = resp.json()
            media_data_url = media_result.get('data')
            media_type = media_result.get('type', 'image')
            mimetype = media_result.get('mimetype', 'image/jpeg')

            ref = ShortUUID().random(length=5)
            caption = f"🔓 *Pesan sekali lihat berhasil dibuka!*\n\n__ref:{ref}__"

            outbox_payload_data = {
                'url': media_data_url,
                'reply_to': inbox.inbox_id,
                'quoted': inbox.data,
            }
            if media_type == 'file' or 'video' in mimetype:
                outbox_payload_data['filename'] = media_result.get('filename', 'media.mp4')
                outbox_payload_data['mimetype'] = mimetype

            Outbox.objects.using('WHATSAPP').create(
                message=caption,
                message_type=media_type if media_type in ('image', 'file') else 'image',
                outbox_for=inbox.inbox_by,
                session_id=inbox.session_id,
                properties=dict(inbox=inbox.inbox_id, reply_to=inbox.inbox_id),
                data=outbox_payload_data,
            )
            _mark_processed(inbox)
            logger.info(f"✅ [RVO COMMAND] Berhasil membuka media sekali lihat untuk {inbox.inbox_by}")
        else:
            err_msg = resp.json().get('error', resp.text) if resp.status_code != 200 else "Gagal mengunduh media"
            logger.warning(f"❌ [RVO COMMAND FAILED] {err_msg}")
            ref = ShortUUID().random(length=5)
            fail_reply = (
                f"❌ *Gagal Membuka Media:*\n{err_msg}\n\n"
                f"💡 *Catatan Penggunaan .rvo:*\n"
                f"• Kirim foto/video sekali lihat *ke nomor bot* atau *ke dalam grup* yang ada botnya.\n"
                f"• Balas (quote/reply) foto tersebut dan ketik *.rvo*.\n"
                f"• Bot harus dalam kondisi aktif saat foto sekali lihat diterima agar dapat mencatat kunci dekripsinya.\n\n"
                f"__ref:{ref}__"
            )
            Outbox.objects.using('WHATSAPP').create(
                message=fail_reply,
                message_type='conversation',
                outbox_for=inbox.inbox_by,
                session_id=inbox.session_id,
                properties=dict(inbox=inbox.inbox_id, reply_to=inbox.inbox_id),
                data=dict(reply_to=inbox.inbox_id, quoted=inbox.data),
            )
            _mark_processed(inbox)

    except Exception as e:
        logger.error(f"❌ [RVO EXCEPTION] Error: {e}", exc_info=True)
        _mark_processed(inbox)


def process_inbox_sync(inbox: Inbox):
    """
    Eksekusi logika pesan masuk secara sinkron (direct execution).
    """
    if not inbox or inbox.is_processed:
        return

    cmd_text = inbox.command or ''
    cmd_normalized = '/'.join(cmd_text.strip().lower().split()) if cmd_text else ''

    # -------------------------------------------------------------
    # 1. Built-in Command: ping
    # -------------------------------------------------------------
    if cmd_normalized in ('ping',):
        ref = ShortUUID().random(length=5)
        reply = f"Pong, saldo saya tidak cukup untuk melayani ping anda.... 😒\n\n__ref:{ref}__"
        Outbox.objects.using('WHATSAPP').create(
            message=reply,
            message_type='conversation',
            outbox_for=inbox.inbox_by,
            session_id=inbox.session_id,
            properties=dict(inbox=inbox.inbox_id, reply_to=inbox.inbox_id),
            data=dict(reply_to=inbox.inbox_id, quoted=inbox.data),
        )
        _mark_processed(inbox)
        logger.info(f"🏓 [BUILTIN COMMAND] 'ping' dijawab untuk {inbox.inbox_by}")
        return

    # -------------------------------------------------------------
    # 2. Built-in Command: whatsapp/info atau info
    # -------------------------------------------------------------
    if cmd_normalized in ('whatsapp/info', 'info'):
        try:
            cpu_pct = psutil.cpu_percent(interval=0.3)
            vmem = psutil.virtual_memory()
            ram_used = round(vmem.used / (1024 ** 3), 2)
            ram_total = round(vmem.total / (1024 ** 3), 2)
            ram_pct = vmem.percent
            disk = psutil.disk_usage('/')
            disk_free = round(disk.free / (1024 ** 3), 2)
            disk_total = round(disk.total / (1024 ** 3), 2)

            ref = ShortUUID().random(length=5)
            info_msg = (
                f"📊 *Informasi Sistem Server:*\n\n"
                f"• *OS:* {platform.system()} {platform.release()}\n"
                f"• *CPU Usage:* {cpu_pct}%\n"
                f"• *RAM:* {ram_used} GB / {ram_total} GB ({ram_pct}%)\n"
                f"• *Disk:* {disk_free} GB Free / {disk_total} GB\n"
                f"• *Waktu Server:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"__ref:{ref}__"
            )
            Outbox.objects.using('WHATSAPP').create(
                message=info_msg,
                message_type='conversation',
                outbox_for=inbox.inbox_by,
                session_id=inbox.session_id,
                properties=dict(inbox=inbox.inbox_id, reply_to=inbox.inbox_id),
                data=dict(reply_to=inbox.inbox_id, quoted=inbox.data),
            )
            _mark_processed(inbox)
            logger.info(f"ℹ️ [BUILTIN COMMAND] 'whatsapp/info' dijawab untuk {inbox.inbox_by}")
            return
        except Exception as err:
            logger.error(f"Error executing whatsapp/info: {err}")

    # -------------------------------------------------------------
    # 3. Dynamic Command Execution via Command & CommandActive
    # -------------------------------------------------------------
    command_active = prepare(inbox)
    if command_active:
        target_cmd = command_active.command.mirror if command_active.command.mirror else command_active.command
        processes = target_cmd.process or []

        for proc in processes:
            logger.info(f"⚡ [EXEC COMMAND] {target_cmd.command} (Type: {target_cmd.command_type})")

            # A. Tipe TXT (Template Formatting)
            if target_cmd.command_type in (Command.Type.TXT, 'txt'):
                try:
                    formatted_msg = proc.format(
                        environment=namedtuple('Environment', os.environ.keys(), rename=True)(*os.environ.values()),
                        setting=djangosettings,
                        now=timezone.now(),
                        inbox=inbox,
                        command_active=command_active,
                    )
                except Exception:
                    formatted_msg = str(proc)

                Outbox.objects.using('WHATSAPP').create(
                    message=formatted_msg,
                    message_type='conversation',
                    outbox_for=inbox.inbox_by,
                    session_id=inbox.session_id,
                    properties=dict(command=target_cmd.pk, inbox=inbox.inbox_id, reply_to=inbox.inbox_id),
                    data=dict(reply_to=inbox.inbox_id, quoted=inbox.data),
                )

            # B. Tipe SQL (Django Template Query Execution)
            elif target_cmd.command_type in (Command.Type.SQL, 'sql'):
                try:
                    from django.template import Context, Template
                    from django.db import connections
                    rendered_sql = Template(str(proc)).render(
                        Context(dict(inbox=inbox, command_active=command_active))
                    )
                    with connections['WHATSAPP'].cursor() as cursor:
                        cursor.execute(rendered_sql)
                    logger.info(f"✅ [SQL EXEC SUCCESS] Query: {rendered_sql[:50]}...")
                except Exception as sql_err:
                    logger.error(f"❌ [SQL EXEC ERROR] {sql_err}", exc_info=True)

            # C. Tipe PY (Dynamic Python Script Execution)
            elif target_cmd.command_type in (Command.Type.PY, 'py'):
                try:
                    result_scope = dict()
                    proc_indented = '\n\t'.join(str(proc).strip().splitlines())
                    exec_code = f"def function():\n\t{proc_indented}".strip()
                    exec(exec_code, dict(
                        inbox=inbox,
                        command_active=command_active,
                    ), result_scope)
                    fn = result_scope[list(result_scope)[-1]]
                    fn()
                    logger.info(f"✅ [PY EXEC SUCCESS] Script executed for {target_cmd.command}")
                except Exception as py_err:
                    logger.error(f"❌ [PY EXEC ERROR] {py_err}", exc_info=True)

        # Jika is_finish == True, bersihkan command active
        if target_cmd.is_finish:
            try:
                command_active.delete(using='WHATSAPP', soft=False)
            except Exception as del_err:
                logger.warning(f"Error deleting CommandActive: {del_err}")

    _mark_processed(inbox)


@huey.db_task(name='Process Inbox Task', queue=ApplicationConfig.name)
def process(inbox: Inbox):
    """
    Task worker asynchronous untuk memproses Inbox via antrean Huey.
    """
    process_inbox_sync(inbox)
