import logging
from django.db import models
from django.db.models import signals
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

from core.fields import ShortUUIDField, StatusField
from core.models import Base
from whatsapp import settings

logger = logging.getLogger(__name__)


class Inbox(Base, ):
    inbox_id = ShortUUIDField(
        length=25,
        max_length=100,
        primary_key=True,
        verbose_name=_('inbox id'),
        help_text=_('Used for identity'),
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
    inbox_by = models.CharField(
        verbose_name=_('inbox by'),
        help_text=_('Used for tracking inbox by'),
    )
    inbox_date = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=_('inbox date'),
        help_text=_('Used for tracking inbox date'),
    )
    is_processed = models.BooleanField(
        default=False,
        verbose_name=_('is processed'),
        help_text=_('Used for detect inbox is processed'),
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
        db_table = u'\"{}\".\"inbox\"'.format(settings.SCHEMA)
        verbose_name = _('Inbox')
        permissions = []

    @property
    def session(self):
        if self.session_id:
            from whatsapp.models import Session
            return Session.objects.using('WHATSAPP').filter(pk=self.session_id).first()
        return None

    @property
    def command(self):
        if self.message:
            lines = self.message.splitlines()
            if lines and lines[0].strip():
                return lines[0].strip()
        return None

    @property
    def parameter(self):
        from core.utils.strings import stringproperties
        parameter = {}
        if self.command:
            try:
                parameter = stringproperties(self.message)
            except Exception:
                parameter = {}
        return parameter


@receiver(signals.post_save, sender=Inbox)
def on_inbox_created(sender, instance: Inbox, created, **kwargs):
    if instance and created and not instance.is_processed:
        try:
            from whatsapp.tasks import process_inbox as process
            process(instance)
        except Exception as e:
            logger.warning(f"Huey enqueue inbox error ({e}), processing directly.")
            try:
                from whatsapp.tasks.inbox import process_inbox_sync
                process_inbox_sync(instance)
            except Exception as sync_err:
                logger.error(f"Error direct processing inbox: {sync_err}", exc_info=True)
