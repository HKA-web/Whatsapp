import logging
from enum import StrEnum

from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import signals
from django.dispatch import receiver
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.fields import IdentifierField, ShortUUIDField, StatusField
from core.models import Base
from whatsapp import settings

logger = logging.getLogger(__name__)


class Command(Base):
    class Type(StrEnum):
        TXT = 'txt'
        SQL = 'sql'
        PY = 'py'

    CommandType = [
        (Type.TXT, _('Command Text')),
        (Type.SQL, _('Command Query SQL')),
        (Type.PY, _('Command Python Script')),
    ]

    command_id = models.CharField(
        max_length=100,
        primary_key=True,
        verbose_name=_('command id'),
        help_text=_('Used for identity'),
    )
    command_name = models.CharField(
        verbose_name=_('command name'),
        help_text=_('Used for view'),
    )
    command = models.CharField(
        verbose_name=_('command'),
        help_text=_('Used for command content'),
    )
    mirror = models.ForeignKey(
        to='self',
        blank=True,
        null=True,
        on_delete=models.CASCADE,
        related_name='children_set',
        db_column='mirror_id',
        verbose_name=_('mirror'),
        help_text=_('Used for linked key as mirror'),
    )
    command_type = models.CharField(
        choices=CommandType,
        verbose_name=_('command type'),
        help_text=_('Used for detect type'),
    )
    process = ArrayField(
        models.TextField(),
        blank=True,
        default=list,
        verbose_name=_('process'),
        help_text=_('Used for process command, can contain plain text, sql, python script, etc'),
    )
    required_parameter = ArrayField(
        models.CharField(),
        blank=True,
        null=True,
        default=list,
        verbose_name=_('required parameter'),
        help_text=_('Used for block inbox use parameter'),
    )
    check_parameter = models.BooleanField(
        default=True,
        verbose_name=_('check parameter'),
        help_text=_('Used for check required parameter'),
    )
    required_permission = ArrayField(
        models.BigIntegerField(),
        blank=True,
        null=True,
        default=list,
        verbose_name=_('required permission'),
        help_text=_('Used for block inbox use permission'),
    )
    check_permission = models.BooleanField(
        default=False,
        verbose_name=_('check permission'),
        help_text=_('Used for check required permission'),
    )
    is_finish = models.BooleanField(
        default=False,
        verbose_name=_('is finish'),
        help_text=_('Used for reset active command'),
    )
    session_id = models.CharField(
        blank=True,
        null=True,
        db_column='session_id',
        verbose_name=_('session'),
        help_text=_('Used for linked key'),
    )
    status = StatusField(transition=False)

    class Meta:
        managed = False
        db_table = u'\"{}\".\"command\"'.format(settings.SCHEMA)
        verbose_name = _('Command')
        permissions = []

    @property
    def session(self):
        if self.session_id:
            from whatsapp.models import Session
            return Session.objects.using('WHATSAPP').filter(pk=self.session_id).first()
        return None

    @property
    def has_children(self):
        return self.children_set.using('WHATSAPP').count() > 0


class CommandActive(Base):
    id = ShortUUIDField(
        length=25,
        primary_key=True,
        verbose_name=_('id'),
        help_text=_('Used for identity'),
    )
    command = models.ForeignKey(
        to=Command,
        on_delete=models.CASCADE,
        related_name='active_commands',
        db_column='command_id',
        verbose_name=_('command'),
        help_text=_('Used for linked key'),
    )
    previous_command = models.ForeignKey(
        to=Command,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name='previous_active_commands',
        db_column='previous_command_id',
        verbose_name=_('previous command'),
        help_text=_('Used for linked key'),
    )
    parameter = models.JSONField(
        default=dict,
        verbose_name=_('parameter'),
        help_text=_('Used for parameter value'),
    )
    command_by = models.CharField(
        verbose_name=_('command by'),
        help_text=_('Used for tracking command by get from inbox'),
    )
    command_date = models.DateTimeField(
        default=timezone.now,
        blank=True,
        null=True,
        verbose_name=_('command date'),
        help_text=_('Used for tracking command date get from inbox'),
    )

    class Meta:
        managed = False
        db_table = u'\"{}\".\"command_active\"'.format(settings.SCHEMA)
        verbose_name = _('Command Active')
        permissions = []


@receiver(signals.pre_save, sender=CommandActive)
def on_command_active_create(sender, instance: CommandActive, **kwargs):
    if instance and instance._state.adding:
        try:
            # Hapus active command sebelumnya untuk pengirim yang sama di sesi yang sama
            session_filter = instance.command.session_id if instance.command else None
            actives = CommandActive.objects.using('WHATSAPP').filter(
                command__session_id=session_filter,
                command_by=instance.command_by,
            )
            for active in actives:
                instance.previous_command = active.command
                active.delete(using='WHATSAPP', soft=False)
                logger.info(f"Updated previous command to {active.command.command}")
        except Exception as e:
            logger.warning(f"Error updating previous CommandActive: {e}")
