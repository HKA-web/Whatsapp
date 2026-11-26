from django.conf import settings
from huey import crontab as cron

import library.djangohuey as huey
from whatsapp.apps import ApplicationConfig
from whatsapp.tasks.outbox import (
    process as process_outbox,
    process_scheduled as process_scheduled_outbox,
)
from whatsapp.tasks.inbox import (
    process as process_inbox,
)

__all__ = [
    process_outbox,
    process_scheduled_outbox,
    process_inbox,
]


default_queue = settings.HUEYS.get('default', list(settings.HUEYS.get('queues', {}).keys())[0] if settings.HUEYS.get('queues') else 'low')
task_queue = ApplicationConfig.name if ApplicationConfig.name in settings.HUEYS.get('queues', {}) else default_queue


@huey.db_periodic_task(cron(minute='*/5'), name=f'Startup All Periodic Task On:{ApplicationConfig.verbose_name}', queue=task_queue, )
def startup():
    from core.tasks.dynamic import startup
    startup(ApplicationConfig, )

