import logging
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.fields import ShortUUIDField, StatusField
from core.models import Base
from whatsapp import settings

logger = logging.getLogger(__name__)


class Sent(Base, ):
    sent_id = ShortUUIDField(
        length=25,
        max_length=100,
        primary_key=True,
        verbose_name=_('sent id'),
        help_text=_('Used for identity'),
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
    sent_for = models.CharField(
        verbose_name=_('sent for'),
        help_text=_('Used for tracking sent for'),
    )
    sent_date = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=_('sent date'),
        help_text=_('Used for tracking sent date'),
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
        db_table = u'\"{}\".\"sent\"'.format(settings.SCHEMA)
        verbose_name = _('Sent')
        permissions = []

    @property
    def session(self):
        if self.session_id:
            from whatsapp.models import Session
            return Session.objects.using('WHATSAPP').filter(pk=self.session_id).first()
        return None

    @property
    def template(self):
        if self.template_id:
            from whatsapp.models import Template
            return Template.objects.using('WHATSAPP').filter(pk=self.template_id).first()
        return None
