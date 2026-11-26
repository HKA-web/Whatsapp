import logging

from django.db.models import Q
from django.utils import timezone
from huey import crontab as cron

import library.djangohuey as huey
from whatsapp.apps import ApplicationConfig
from whatsapp import settings
from whatsapp.models import Outbox

logger = logging.getLogger(__name__)


@huey.db_task(name='Process Outbox Task', queue=ApplicationConfig.name, )
def process(outbox: Outbox, ):
    if outbox and not outbox.scheduled:
        if outbox.prepare_date is None:
            setattr(outbox, 'prepare_date', timezone.now())
            
        setattr(outbox, 'retry', outbox.retry + 1)
        outbox.save(using='WHATSAPP', update_fields=['prepare_date', 'retry', ])
        outbox.send()


@huey.db_periodic_task(cron(minute='*'), name='Process Scheduled Outbox Task', queue=ApplicationConfig.name, )
def process_scheduled():
    outbox_cfg = getattr(settings, 'OUTBOX', {}) if isinstance(getattr(settings, 'OUTBOX', {}), dict) else {}
    retry_maximum = int(outbox_cfg.get('RETRY', 3))
    retry_delay_minutes = int(outbox_cfg.get('DELAY', 5))
    retry_blast = bool(outbox_cfg.get('RETRY_BLAST', True))
    batch_size = int(outbox_cfg.get('BATCH_SIZE', 50))

    now = timezone.now()
    cool_down_time = now - timezone.timedelta(minutes=retry_delay_minutes)

    # Kriteria pesan yang memenuhi syarat untuk diproses:
    # 1. Pesan baru (retry == 0):
    #    - Pesan unscheduled yang belum terkirim, ATAU
    #    - Pesan scheduled yang waktu jadwalnya sudah tiba (scheduled_date <= now)
    # 2. Pesan gagal/retry (retry > 0 dan retry <= retry_maximum):
    #    - Sudah melewati masa jeda tunggu (prepare_date <= now - DELAY)
    eligible_q = (
        (Q(retry=0) & (Q(scheduled=False) | Q(scheduled=True, scheduled_date__lte=now)))
        |
        (Q(retry__gt=0, retry__lte=retry_maximum, prepare_date__lte=cool_down_time))
    )

    queryset = Outbox.objects.using('WHATSAPP').filter(eligible_q)

    if retry_blast:
        queryset = queryset.filter(~Q(properties__has_key='blast'))

    # Prioritaskan pesan dengan retry terkecil terlebih dahulu (0, lalu 1, lalu 2, dst.),
    # kemudian diurutkan berdasarkan waktu pembuatan pesan tertua (FIFO).
    # Jika 50 pesan pertama gagal (retry naik jadi 1+), maka 50 berikutnya yang diambil
    # otomatis adalah pesan yang memiliki retry lebih kecil!
    outbox_batch = list(queryset.order_by('retry', 'created')[:batch_size])

    if outbox_batch:
        logger.info(f"🔄 [OUTBOX SCHEDULED] Memproses {len(outbox_batch)} pesan (Batch size: {batch_size})...")

    for outbox in outbox_batch:
        outbox.prepare_date = now
        outbox.retry = outbox.retry + 1
        outbox.save(using='WHATSAPP', update_fields=['prepare_date', 'retry'])
        outbox.send()

