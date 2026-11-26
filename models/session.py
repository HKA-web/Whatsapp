import logging
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.fields import ShortUUIDField, StatusField
from core.models import Base
from whatsapp import settings

logger = logging.getLogger(__name__)


class Session(Base, ):
    session_id = ShortUUIDField(
        length=25,
        primary_key=True,
        verbose_name=_('session id'),
        help_text=_('Used for identity'),
    )
    session_name = models.CharField(
        verbose_name=_('session name'),
        help_text=_('Used for view'),
    )
    data = models.JSONField(
        default=dict,
        verbose_name=_('data'),
        help_text=_('Used for data value'),
    )
    premised = models.BooleanField(
        default=True,
        verbose_name=_('premised'),
        help_text=_('Used for whatsapp is on premise server'),
    )
    server = models.CharField(
        blank=True,
        null=True,
        verbose_name=_('server'),
        help_text=_('Used for url server if not premised'),
    )
    status = StatusField(transition=False, )

    class Meta:
        managed = False
        db_table = u'\"{}\".\"session\"'.format(settings.SCHEMA)
        verbose_name = _('Session')
        permissions = []