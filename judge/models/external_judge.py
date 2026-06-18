import logging

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


logger = logging.getLogger('judge.external_judge')


def _fernet():
    key = getattr(settings, 'EXTERNAL_JUDGE_ENCRYPTION_KEY', None)
    if not key:
        raise ImproperlyConfigured('EXTERNAL_JUDGE_ENCRYPTION_KEY is required for external judge tokens.')
    if isinstance(key, str):
        key = key.encode('ascii')
    return Fernet(key)


def encrypt_external_token(raw_token):
    raw_token = (raw_token or '').strip()
    if not raw_token:
        raise ValidationError(_('External judge API token is required.'))
    return _fernet().encrypt(raw_token.encode('utf-8')).decode('ascii')


def decrypt_external_token(encrypted_token):
    encrypted_token = (encrypted_token or '').strip()
    if not encrypted_token:
        raise ValidationError(_('External judge API token is not configured.'))
    try:
        return _fernet().decrypt(encrypted_token.encode('ascii')).decode('utf-8')
    except InvalidToken:
        logger.exception('External judge API token could not be decrypted.')
        raise ValidationError(_('External judge API token could not be decrypted.'))


def token_display_prefix(raw_token):
    raw_token = (raw_token or '').strip()
    if not raw_token:
        return ''
    if len(raw_token) <= 8:
        return raw_token
    return '%s...' % raw_token[:8]


class ExternalJudgeConfig(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name=_('name'))
    base_url = models.URLField(
        verbose_name=_('base URL'),
        help_text=_('PCD VJudge API base URL, e.g. https://vjudge.example.com'),
    )
    encrypted_api_token = models.TextField(verbose_name=_('encrypted API token'))
    token_prefix = models.CharField(max_length=20, blank=True, verbose_name=_('token prefix'))
    is_active = models.BooleanField(default=True, verbose_name=_('is active'))
    timeout_seconds = models.PositiveIntegerField(default=30, verbose_name=_('submit timeout seconds'))
    poll_timeout_seconds = models.PositiveIntegerField(default=10, verbose_name=_('poll timeout seconds'))
    poll_interval_seconds = models.PositiveIntegerField(default=5, verbose_name=_('poll interval seconds'))
    max_poll_attempts = models.PositiveIntegerField(default=120, verbose_name=_('max poll attempts'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('created at'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('updated at'))
    last_verified_at = models.DateTimeField(null=True, blank=True, verbose_name=_('last verified at'))

    class Meta:
        verbose_name = _('External Judge Configuration')
        verbose_name_plural = _('External Judge Configurations')

    def __str__(self):
        return self.name

    def get_api_token(self):
        return decrypt_external_token(self.encrypted_api_token)

    def set_api_token(self, raw_token):
        self.encrypted_api_token = encrypt_external_token(raw_token)
        self.token_prefix = token_display_prefix(raw_token)

    def mark_verified(self):
        self.last_verified_at = timezone.now()


class ExternalProblem(models.Model):
    problem = models.OneToOneField(
        'judge.Problem',
        on_delete=models.CASCADE,
        related_name='external_problem',
        verbose_name=_('problem'),
    )
    config = models.ForeignKey(
        ExternalJudgeConfig,
        on_delete=models.SET_NULL,
        null=True,
        related_name='problems',
        verbose_name=_('configuration'),
    )
    oj = models.CharField(max_length=50, verbose_name=_('OJ identifier'))
    external_problem_id = models.CharField(max_length=100, verbose_name=_('external problem ID'))
    is_active = models.BooleanField(default=True, verbose_name=_('is active'))
    metadata_cache = models.JSONField(default=dict, blank=True, verbose_name=_('metadata cache'))
    language_mappings = models.JSONField(default=list, blank=True, verbose_name=_('language mappings'))
    last_synced_at = models.DateTimeField(null=True, blank=True, verbose_name=_('last synced at'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('created at'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('updated at'))

    class Meta:
        verbose_name = _('External Problem')
        verbose_name_plural = _('External Problems')
        indexes = [
            models.Index(fields=['config', 'oj', 'external_problem_id']),
        ]

    def __str__(self):
        return '%s -> %s %s' % (self.problem.code, self.oj, self.external_problem_id)

    @property
    def is_available(self):
        return self.is_active and self.config_id is not None and self.config and self.config.is_active

    def get_language_mapping(self, language):
        key = getattr(language, 'key', language)
        key = str(key or '').strip().lower()
        for mapping in self.language_mappings or []:
            if str(mapping.get('qhhoj_key') or '').strip().lower() == key:
                return mapping
        return None


class ExternalSubmission(models.Model):
    submission = models.OneToOneField(
        'judge.Submission',
        on_delete=models.CASCADE,
        related_name='external_submission',
        verbose_name=_('submission'),
    )
    config = models.ForeignKey(
        ExternalJudgeConfig,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_('configuration'),
    )
    pcd_submission_id = models.UUIDField(verbose_name=_('PCD submission ID'))
    pcd_system_status = models.CharField(max_length=30, default='pending', verbose_name=_('PCD system status'))
    pcd_status_canonical = models.CharField(
        max_length=30,
        null=True,
        blank=True,
        verbose_name=_('PCD canonical status'),
    )
    pcd_vjudge_run_id = models.CharField(max_length=100, null=True, blank=True, verbose_name=_('VJudge run ID'))
    pcd_remote_url = models.URLField(max_length=1000, null=True, blank=True, verbose_name=_('remote URL'))
    pcd_runtime_ms = models.IntegerField(null=True, blank=True, verbose_name=_('runtime milliseconds'))
    pcd_memory_kb = models.IntegerField(null=True, blank=True, verbose_name=_('memory KB'))
    pcd_score_text = models.CharField(max_length=100, null=True, blank=True, verbose_name=_('score text'))
    last_polled_at = models.DateTimeField(null=True, blank=True, verbose_name=_('last polled at'))
    poll_attempts = models.PositiveIntegerField(default=0, verbose_name=_('poll attempts'))
    raw_response = models.JSONField(default=dict, blank=True, verbose_name=_('raw response'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('created at'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('updated at'))

    class Meta:
        verbose_name = _('External Submission')
        verbose_name_plural = _('External Submissions')

    def __str__(self):
        return 'External submission %s' % self.submission_id
