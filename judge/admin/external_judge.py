from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from judge.models import ExternalJudgeConfig, ExternalProblem, ExternalSubmission
from judge.utils.external_judge_client import ExternalJudgeClient, ExternalJudgeError, user_safe_message


class ExternalJudgeConfigAdminForm(forms.ModelForm):
    api_token = forms.CharField(
        label=_('API token'),
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text=_('Leave blank when editing to keep the existing token.'),
    )

    class Meta:
        model = ExternalJudgeConfig
        fields = (
            'name',
            'base_url',
            'api_token',
            'is_active',
            'timeout_seconds',
            'poll_timeout_seconds',
            'poll_interval_seconds',
            'max_poll_attempts',
        )

    def clean(self):
        cleaned_data = super().clean()
        api_token = cleaned_data.get('api_token')
        if not self.instance.pk and not api_token:
            raise ValidationError(_('API token is required for a new external judge configuration.'))
        if cleaned_data.get('base_url') and (api_token or self.instance.encrypted_api_token):
            probe = ExternalJudgeConfig(
                name=cleaned_data.get('name') or self.instance.name,
                base_url=cleaned_data.get('base_url') or self.instance.base_url,
                is_active=cleaned_data.get('is_active'),
                timeout_seconds=cleaned_data.get('timeout_seconds') or 30,
                poll_timeout_seconds=cleaned_data.get('poll_timeout_seconds') or 10,
                poll_interval_seconds=cleaned_data.get('poll_interval_seconds') or 5,
                max_poll_attempts=cleaned_data.get('max_poll_attempts') or 120,
            )
            if api_token:
                probe.set_api_token(api_token)
            else:
                probe.encrypted_api_token = self.instance.encrypted_api_token
            try:
                ExternalJudgeClient(probe).verify_connection()
            except ExternalJudgeError as exc:
                raise ValidationError(user_safe_message(exc))
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        api_token = self.cleaned_data.get('api_token')
        if api_token:
            instance.set_api_token(api_token)
        if commit:
            instance.save()
        return instance


@admin.register(ExternalJudgeConfig)
class ExternalJudgeConfigAdmin(admin.ModelAdmin):
    form = ExternalJudgeConfigAdminForm
    list_display = ('name', 'base_url', 'token_prefix', 'is_active', 'last_verified_at', 'updated_at')
    list_filter = ('is_active',)
    readonly_fields = ('encrypted_api_token', 'token_prefix', 'last_verified_at', 'created_at', 'updated_at')

    def save_model(self, request, obj, form, change):
        obj.last_verified_at = timezone.now()
        super().save_model(request, obj, form, change)


@admin.register(ExternalProblem)
class ExternalProblemAdmin(admin.ModelAdmin):
    list_display = ('problem', 'config', 'oj', 'external_problem_id', 'is_active', 'last_synced_at', 'updated_at')
    list_filter = ('is_active', 'oj', 'config')
    search_fields = ('problem__code', 'problem__name', 'oj', 'external_problem_id')
    readonly_fields = ('metadata_cache', 'language_mappings', 'last_synced_at', 'created_at', 'updated_at')


@admin.register(ExternalSubmission)
class ExternalSubmissionAdmin(admin.ModelAdmin):
    list_display = (
        'submission',
        'config',
        'pcd_submission_id',
        'pcd_system_status',
        'pcd_status_canonical',
        'poll_attempts',
        'updated_at',
    )
    list_filter = ('pcd_system_status', 'pcd_status_canonical', 'config')
    search_fields = ('submission__id', 'pcd_submission_id', 'pcd_vjudge_run_id')
    readonly_fields = [field.name for field in ExternalSubmission._meta.fields]

    def has_add_permission(self, request):
        return False
