import logging
import sys

from django.conf import settings as djangosettings
from whatsapp.apps import ApplicationConfig

logger = logging.getLogger(__name__)

DEFAULTS = dict(
    SECRET_KEY=str(getattr(djangosettings, 'SECRET_KEY', '')),
    SCHEMA=ApplicationConfig.name,
    WEBHOOK_URL=getattr(djangosettings, 'WHATSAPP.WEBHOOK_URL', ''),
    PORT = getattr(djangosettings, 'WHATSAPP.PORT', ''),
    SESSION=None,
    CONFIG=None,
    OUTBOX=dict(
        RETRY=3,
        DELAY=5,
        RETRY_BLAST=True,
        BATCH_SIZE=50,
    ),
)
__all__ = list(DEFAULTS)


def load():
    module = sys.modules[__name__]
    for name, default in DEFAULTS.items():
        setattr(module, name, getattr(djangosettings, ApplicationConfig.name.upper(), {}).get(name, default))
    if module.CONFIG and isinstance(module.CONFIG, dict):
        if 'webhook' not in module.CONFIG:
            module.CONFIG.update(webhook=dict(), )
        module.CONFIG['webhook'].update(
            webSocket=module.CONFIG['webhook'].get('webSocket', False),
            webSocketMsgPack=module.CONFIG['webhook'].get('webSocketMsgPack', getattr(djangosettings, 'CHANNEL_MSGPACK', True)),
        )


load()