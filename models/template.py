import logging

from django.db import models
from django.db.models import signals
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

from core.fields import ShortUUIDField, StatusField
from core.models import Base
from whatsapp import settings

logger = logging.getLogger(__name__)


class Template(Base, ):
    template_id = ShortUUIDField(
        length=25,
        max_length=100,
        primary_key=True,
        verbose_name=_('template id'),
        help_text=_('Used for identity'),
    )
    template_name = models.CharField(
        verbose_name=_('template name'),
        help_text=_('Used for view'),
    )
    template = models.TextField(
        verbose_name=_('template'),
        help_text=_('Used for content, only django template language'),
    )
    session_id = models.CharField(
        verbose_name=_('session'),
        help_text=_('Used for linked key'),
    )
    status = StatusField(transition=False, )

    class Meta:
        managed = False
        db_table = u'\"{}\".\"template\"'.format(settings.SCHEMA)
        verbose_name = _('Template')
        permissions = []

    @property
    def session(self):
        if self.session_id:
            from whatsapp.models import Session
            return Session.objects.using('WHATSAPP').filter(pk=self.session_id).first()
        return None

@receiver(signals.pre_save, sender=Template, )
def on_session_before_create(sender, instance: Template, **kwargs, ):
    if instance:
        if instance._state.adding:
            pass
