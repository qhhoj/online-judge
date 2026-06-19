import json
import mimetypes
import os
from itertools import chain
from zipfile import (
    BadZipfile,
    ZipFile,
)

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.forms import (
    BaseModelFormSet,
    BooleanField,
    CharField,
    ChoiceField,
    HiddenInput,
    ModelChoiceField,
    ModelForm,
    NumberInput,
    RadioSelect,
    Select,
    Textarea,
    formset_factory,
)
from django.http import (
    Http404,
    HttpResponse,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import (
    get_object_or_404,
    render,
)
from django.urls import reverse
from django.utils import timezone
from django.utils.html import (
    escape,
    format_html,
)
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.generic import DetailView

from judge.highlight_code import highlight_code
from judge.models import (
    ExternalJudgeConfig,
    ExternalProblem,
    Language,
    Problem,
    ProblemData,
    ProblemTestCase,
    Submission,
    problem_data_storage,
)
from judge.models.problem_data import (
    CUSTOM_CHECKERS,
    IO_METHODS,
)
from judge.utils.external_judge_client import ExternalJudgeClient, ExternalJudgeError, user_safe_message
from judge.utils.problem_data import ProblemDataCompiler
from judge.utils.problem_mirror import (
    get_mirrorable_source_queryset,
    get_problem_single_organization,
    sync_mirror_archive_for_problem,
    validate_mirror_source_for_target,
)
from judge.utils.unicode import utf8text
from judge.utils.views import (
    TitleMixin,
    add_file_response,
    generic_message,
)
from judge.views.problem import ProblemMixin
from judge.widgets import Select2Widget


mimetypes.init()
mimetypes.add_type('application/x-yaml', '.yml')


def _can_download_problem_data(user, problem):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if problem.is_mirror and problem.mirror_root_id:
        return problem.mirror_root.is_editable_by(user)
    return problem.is_editable_by(user)


def checker_args_cleaner(self):
    data = self.cleaned_data['checker_args']
    if not data or data.isspace():
        return ''
    try:
        if not isinstance(json.loads(data), dict):
            raise ValidationError(_('Checker arguments must be a JSON object.'))
    except ValueError:
        raise ValidationError(_('Checker arguments is invalid JSON.'))
    return data


def grader_args_cleaner(self):
    data = self.cleaned_data['grader_args']
    if not data or data.isspace():
        return ''
    try:
        if not isinstance(json.loads(data), dict):
            raise ValidationError(_('Grader arguments must be a JSON object'))
    except ValueError:
        raise ValidationError(_('Grader arguments is invalid JSON'))
    return data


class ProblemDataForm(ModelForm):
    io_method = ChoiceField(
        choices=IO_METHODS, label=gettext_lazy('IO Method'), initial='standard', required=False,
        widget=Select2Widget(attrs={'style': 'width: 200px'}),
    )
    io_input_file = CharField(max_length=100, label=gettext_lazy('Input from file'), required=False)
    io_output_file = CharField(max_length=100, label=gettext_lazy('Output to file'), required=False)
    checker_type = ChoiceField(choices=CUSTOM_CHECKERS, widget=Select2Widget(attrs={'style': 'width: 200px'}))

    def clean_zipfile(self):
        if hasattr(self, 'zip_valid') and not self.zip_valid:
            raise ValidationError(_('Your zip file is invalid!'))
        return self.cleaned_data['zipfile']

    clean_checker_args = checker_args_cleaner
    clean_grader_args = grader_args_cleaner

    class Meta:
        model = ProblemData
        fields = [
            'zipfile',
            'grader', 'io_method', 'io_input_file', 'io_output_file',
            'custom_grader', 'custom_header', 'grader_args',
            'checker', 'custom_checker', 'checker_args', 'checker_type',
            'output_limit',
        ]
        widgets = {
            'checker_args': HiddenInput,
            'checker': Select2Widget(attrs={'style': 'width: 200px'}),
            'grader': Select2Widget(attrs={'style': 'width: 200px'}),
        }
        help_texts = {
            'output_limit': _('Can be left blank. In case the output can be too long (over 20MB), please set this.'),
        }


class ProblemCaseForm(ModelForm):
    clean_checker_args = checker_args_cleaner

    class Meta:
        model = ProblemTestCase
        fields = (
            'order', 'type', 'input_file', 'output_file', 'points',
            'is_pretest',  # 'output_limit', 'output_prefix',
            'checker', 'checker_args', 'generator_args',
        )
        widgets = {
            'generator_args': HiddenInput,
            'type': Select(attrs={'style': 'width: 100%'}),
            'points': NumberInput(attrs={'style': 'width: 4em'}),
            # 'output_prefix': NumberInput(attrs={'style': 'width: 4.5em'}),
            # 'output_limit': NumberInput(attrs={'style': 'width: 6em'}),
            'checker_args': HiddenInput,
        }


class ProblemCaseFormSet(
    formset_factory(
        ProblemCaseForm, formset=BaseModelFormSet, extra=0, max_num=1,
        can_delete=True,
    ),
):
    model = ProblemTestCase

    def __init__(self, *args, **kwargs):
        self.valid_files = kwargs.pop('valid_files', None)
        super(ProblemCaseFormSet, self).__init__(*args, **kwargs)

    def _construct_form(self, i, **kwargs):
        form = super(ProblemCaseFormSet, self)._construct_form(i, **kwargs)
        form.valid_files = self.valid_files
        return form


class ExternalJudgeForm(ModelForm):
    enabled = BooleanField(required=False, label=gettext_lazy('Enable Virtual Judge'))
    config = ModelChoiceField(
        queryset=ExternalJudgeConfig.objects.filter(is_active=True),
        required=False,
        label=gettext_lazy('VJudge server'),
        widget=Select2Widget(attrs={'style': 'width: 260px'}),
    )
    language_mappings = CharField(
        required=False,
        label=gettext_lazy('Language mappings'),
        widget=Textarea(attrs={'rows': 4, 'style': 'display: none;'}),
    )
    metadata_cache = CharField(required=False, widget=HiddenInput)

    class Meta:
        model = ExternalProblem
        fields = ('config', 'oj', 'external_problem_id', 'language_mappings', 'metadata_cache')

    def __init__(self, *args, **kwargs):
        self.problem = kwargs.pop('problem')
        self.enabled_override = kwargs.pop('enabled_override', None)
        super(ExternalJudgeForm, self).__init__(*args, **kwargs)
        self.fields['oj'].required = False
        self.fields['external_problem_id'].required = False
        if self.instance.pk:
            self.initial['enabled'] = self.instance.is_active
            self.initial['language_mappings'] = json.dumps(self.instance.language_mappings or [], ensure_ascii=False)
            self.initial['metadata_cache'] = json.dumps(self.instance.metadata_cache or {}, ensure_ascii=False)

    def clean(self):
        cleaned_data = super(ExternalJudgeForm, self).clean()
        enabled = (
            self.enabled_override
            if self.enabled_override is not None
            else cleaned_data.get('enabled')
        )
        cleaned_data['enabled'] = enabled
        if enabled:
            for field in ('config', 'oj', 'external_problem_id'):
                if not cleaned_data.get(field):
                    self.add_error(field, _('This field is required when Virtual Judge is enabled.'))

        raw_mappings = cleaned_data.get('language_mappings') or '[]'
        try:
            mappings = json.loads(raw_mappings)
        except ValueError:
            raise ValidationError(_('Language mappings must be valid JSON.'))
        if not isinstance(mappings, list):
            raise ValidationError(_('Language mappings must be a JSON list.'))

        language_keys = {
            key.lower(): key for key in Language.objects.order_by('key').values_list('key', flat=True)
        }
        normalized = []
        invalid_qhhoj_keys = []
        for mapping in mappings:
            if not isinstance(mapping, dict):
                continue
            qhhoj_key = (mapping.get('qhhoj_key') or '').strip()
            vjudge_id = str(mapping.get('vjudge_id') or mapping.get('vjudge_language_id') or '').strip()
            vjudge_name = (mapping.get('vjudge_name') or '').strip()
            if qhhoj_key and vjudge_id:
                canonical_qhhoj_key = language_keys.get(qhhoj_key.lower())
                if enabled and canonical_qhhoj_key is None:
                    invalid_qhhoj_keys.append(qhhoj_key)
                    continue
                normalized.append({
                    'qhhoj_key': canonical_qhhoj_key or qhhoj_key,
                    'vjudge_id': vjudge_id,
                    'vjudge_name': vjudge_name,
                })
        if invalid_qhhoj_keys:
            self.add_error(
                'language_mappings',
                _('Unknown QHHOJ language key(s): %(keys)s. Use an existing language key.') % {
                    'keys': ', '.join(sorted(set(invalid_qhhoj_keys))),
                },
            )
        if enabled and not normalized and not invalid_qhhoj_keys:
            raise ValidationError(_('At least one language mapping is required when Virtual Judge is enabled.'))
        cleaned_data['language_mappings'] = normalized
        raw_metadata = cleaned_data.get('metadata_cache') or '{}'
        try:
            metadata = json.loads(raw_metadata)
        except ValueError:
            metadata = {}
        cleaned_data['metadata_cache'] = metadata if isinstance(metadata, dict) else {}
        return cleaned_data

    def save(self, commit=True):
        if self.instance.pk:
            instance = super(ExternalJudgeForm, self).save(commit=False)
        else:
            instance = ExternalProblem(problem=self.problem)
        instance.config = self.cleaned_data.get('config')
        instance.oj = self.cleaned_data.get('oj') or instance.oj or ''
        instance.external_problem_id = (
            self.cleaned_data.get('external_problem_id') or instance.external_problem_id or ''
        )
        instance.metadata_cache = self.cleaned_data.get('metadata_cache') or instance.metadata_cache or {}
        if instance.metadata_cache:
            instance.last_synced_at = timezone.now()
        instance.language_mappings = self.cleaned_data.get('language_mappings') or []
        instance.is_active = self.cleaned_data.get('enabled')
        if commit:
            instance.save()
        return instance


class ProblemMirrorForm(ModelForm):
    TEST_SOURCE_LOCAL = 'local'
    TEST_SOURCE_MIRROR = 'mirror'
    TEST_SOURCE_EXTERNAL = 'external'
    TEST_SOURCE_CHOICES = (
        (TEST_SOURCE_LOCAL, gettext_lazy('Uploaded test data')),
        (TEST_SOURCE_MIRROR, gettext_lazy('Mirror another problem')),
        (TEST_SOURCE_EXTERNAL, gettext_lazy('Virtual Judge')),
    )

    test_source = ChoiceField(
        choices=TEST_SOURCE_CHOICES,
        label=gettext_lazy('Test source'),
        widget=RadioSelect,
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        target_problem = self.instance if (self.instance and self.instance.pk) else None
        target_org = get_problem_single_organization(target_problem) if target_problem is not None else None
        self.fields['mirror_of'].required = False
        self.fields['mirror_of'].empty_label = 'None'
        self.fields['mirror_of'].label_from_instance = lambda obj: '%s - %s' % (obj.code, obj.name)
        if not self.is_bound:
            if target_problem and target_problem.has_external_problem:
                self.initial['test_source'] = self.TEST_SOURCE_EXTERNAL
            elif target_problem and target_problem.is_mirror:
                self.initial['test_source'] = self.TEST_SOURCE_MIRROR
            else:
                self.initial['test_source'] = self.TEST_SOURCE_LOCAL

        if target_problem and target_problem.is_mirror:
            self.fields['mirror_of'].queryset = Problem.objects.filter(id=target_problem.mirror_of_id)
        else:
            self.fields['mirror_of'].queryset = get_mirrorable_source_queryset(
                self.user,
                target_problem=target_problem,
                target_org=target_org,
            )

        if target_problem is not None and target_problem.mirror_of_id is not None:
            self.fields['mirror_of'].queryset = (
                self.fields['mirror_of'].queryset | Problem.objects.filter(pk=target_problem.mirror_of_id)
            ).distinct()
        choices = list(self.fields['mirror_of'].choices)
        if choices and isinstance(choices[0], tuple) and len(choices[0]) >= 2:
            empty_choice = (choices[0][0], _('None'))
            choices[0] = empty_choice
            self.fields['mirror_of'].choices = choices

    def clean_mirror_of(self):
        if self.data.get(self.add_prefix('test_source')) != self.TEST_SOURCE_MIRROR:
            return None
        mirror_of = self.cleaned_data.get('mirror_of')
        target_problem = self.instance if (self.instance and self.instance.pk) else None
        target_org = get_problem_single_organization(target_problem) if target_problem is not None else None
        validate_mirror_source_for_target(
            user=self.user,
            source=mirror_of,
            target_problem=target_problem,
            target_org=target_org,
        )
        return mirror_of

    def clean(self):
        cleaned_data = super().clean()
        test_source = cleaned_data.get('test_source')
        mirror_of = cleaned_data.get('mirror_of')
        if test_source == self.TEST_SOURCE_MIRROR:
            if mirror_of is None:
                self.add_error('mirror_of', _('Select a source problem for Mirror test data.'))
        else:
            cleaned_data['mirror_of'] = None
        return cleaned_data

    class Meta:
        model = Problem
        fields = ('test_source', 'mirror_of')
        widgets = {
            'mirror_of': Select2Widget(attrs={
                'style': 'width: 100%',
                'data-allow-clear': 'true',
            }),
        }
        help_texts = {
            'mirror_of': _(
                'Select a source problem to mirror test archive from. '
                'Leave empty to use this problem data.',
            ),
        }


class ProblemManagerMixin(LoginRequiredMixin, ProblemMixin, DetailView):
    def get_object(self, queryset=None):
        problem = super(ProblemManagerMixin, self).get_object(queryset)
        if problem.is_manually_managed:
            raise Http404()
        if self.request.user.is_superuser or problem.is_editable_by(self.request.user):
            return problem
        raise Http404()


class ProblemSubmissionDiff(TitleMixin, ProblemMixin, DetailView):
    template_name = 'problem/submission-diff.html'

    def get_title(self):
        return _('Comparing submissions for {0}').format(self.object.name)

    def get_content_title(self):
        return mark_safe(
            escape(
                _('Comparing submissions for {0}')).format(
                format_html(
                    '<a href="{1}">{0}</a>',
                    self.object.name,
                    reverse(
                        'problem_detail',
                        args=[
                            self.object.code])),
            ),
        )

    def get_object(self, queryset=None):
        problem = super(ProblemSubmissionDiff, self).get_object(queryset)
        if problem.is_editable_by(self.request.user):
            return problem
        raise Http404()

    def get_context_data(self, **kwargs):
        context = super(ProblemSubmissionDiff, self).get_context_data(**kwargs)

        subs = None
        if 'username' in self.request.GET:
            usernames = self.request.GET.getlist('username')
            subs = Submission.objects.filter(problem=self.object, user__user__username__in=usernames)
        elif 'id' in self.request.GET:
            ids = self.request.GET.getlist('id')
            subs = Submission.objects.filter(problem=self.object, id__in=ids)

        if not subs:
            raise Submission.DoesNotExist()

        subs = subs.order_by('id')
        context['submissions'] = subs.filter(language__file_only=False)

        # If we have associated data we can do better than just guess
        data = ProblemTestCase.objects.filter(dataset=self.object, type='C')
        if data:
            num_cases = data.count()
        else:
            num_cases = subs.first().test_cases.count()
        context['num_cases'] = num_cases
        return context

    def get(self, request, *args, **kwargs):
        try:
            return super(ProblemSubmissionDiff, self).get(request, *args, **kwargs)
        except Submission.DoesNotExist:
            return generic_message(self.request, _('No such submissions'), _('Could not find any submissions.'))


class ProblemDataView(TitleMixin, ProblemManagerMixin):
    template_name = 'problem/data.html'

    def get_title(self):
        return _('Editing data for {0}').format(self.object.name)

    def get_content_title(self):
        return mark_safe(
            escape(_('Editing data for %s')) % (
                format_html(
                    '<a href="{1}">{0}</a>', self.object.name,
                    reverse('problem_detail', args=[self.object.code]),
                )
            ),
        )

    def get_data_form(self, post=False):
        data_instance, _ = ProblemData.objects.get_or_create(problem=self.object)
        return ProblemDataForm(
            data=self.request.POST if post else None, prefix='problem-data',
            files=self.request.FILES if post else None,
            instance=data_instance,
        )

    def get_case_formset(self, files, post=False):
        return ProblemCaseFormSet(
            data=self.request.POST if post else None, prefix='cases', valid_files=files,
            queryset=ProblemTestCase.objects.filter(dataset_id=self.object.pk).order_by('order'),
        )

    def get_mirror_form(self, post=False):
        return ProblemMirrorForm(
            data=self.request.POST if post else None,
            prefix='mirror',
            instance=self.object,
            user=self.request.user,
        )

    def get_external_form(self, post=False, enabled_override=None):
        try:
            instance = self.object.external_problem
        except ExternalProblem.DoesNotExist:
            instance = ExternalProblem(problem=self.object)
        return ExternalJudgeForm(
            data=self.request.POST if post else None,
            prefix='external',
            instance=instance,
            problem=self.object,
            enabled_override=enabled_override,
        )

    def _get_archive_provider_data(self, data):
        if not self.object.is_mirror or not self.object.mirror_root_id:
            return data
        root_data, _ = ProblemData.objects.get_or_create(problem=self.object.mirror_root)
        return root_data

    def _bootstrap_mirror_config_from_root(self):
        if not self.object.is_mirror or not self.object.mirror_root_id:
            return

        mirror_data, _ = ProblemData.objects.get_or_create(problem=self.object)
        root_data, _ = ProblemData.objects.get_or_create(problem=self.object.mirror_root)

        fields = (
            'output_prefix',
            'output_limit',
            'checker',
            'grader',
            'unicode',
            'nobigmath',
            'checker_args',
            'grader_args',
        )
        changed_fields = []
        for field in fields:
            root_value = getattr(root_data, field)
            if getattr(mirror_data, field) != root_value:
                setattr(mirror_data, field, root_value)
                changed_fields.append(field)
        if changed_fields:
            mirror_data.save(update_fields=changed_fields)

    def _copy_cases_if_missing_from_root(self):
        if not self.object.is_mirror or not self.object.mirror_root_id:
            return
        if ProblemTestCase.objects.filter(dataset_id=self.object.id).exists():
            return

        rows = []
        for case in self.object.mirror_root.cases.order_by('order'):
            rows.append(ProblemTestCase(
                dataset=self.object,
                order=case.order,
                type=case.type,
                input_file=case.input_file,
                output_file=case.output_file,
                generator_args=case.generator_args,
                points=case.points,
                is_pretest=case.is_pretest,
                output_prefix=case.output_prefix,
                output_limit=case.output_limit,
                checker=case.checker,
                checker_args=case.checker_args,
            ))
        if rows:
            ProblemTestCase.objects.bulk_create(rows)

    def _save_cases_formset(self, problem, cases_formset):
        for case in cases_formset.save(commit=False):
            case.dataset_id = problem.id
            case.save()
        for case in cases_formset.deleted_objects:
            case.delete()

    def get_valid_files(self, data, post=False):
        archive_data = self._get_archive_provider_data(data)
        try:
            if post and 'problem-data-zipfile-clear' in self.request.POST:
                return []
            elif post and 'problem-data-zipfile' in self.request.FILES:
                return ZipFile(self.request.FILES['problem-data-zipfile']).namelist()
            elif archive_data.zipfile:
                return ZipFile(archive_data.zipfile.path).namelist()
        except (BadZipfile, OSError):
            return []
        return []

    def get_context_data(self, **kwargs):
        context = super(ProblemDataView, self).get_context_data(**kwargs)
        if 'data_form' not in context:
            self._copy_cases_if_missing_from_root()
            context['data_form'] = self.get_data_form()
            valid_files = context['valid_files'] = self.get_valid_files(context['data_form'].instance)
            context['data_form'].zip_valid = valid_files is not False
            context['cases_formset'] = self.get_case_formset(valid_files)
        if 'mirror_form' not in context:
            context['mirror_form'] = self.get_mirror_form()
        if 'external_form' not in context:
            context['external_form'] = self.get_external_form()
        context['valid_files_json'] = mark_safe(json.dumps(context['valid_files']))
        context['valid_files'] = set(context['valid_files'])
        context['all_case_forms'] = chain(context['cases_formset'], [context['cases_formset'].empty_form])

        if self.request.user.has_perm('judge.create_mass_testcases'):
            context['testcase_limit'] = 9999
            context['testcase_soft_limit'] = 9999
        else:
            context['testcase_limit'] = settings.VNOJ_TESTCASE_HARD_LIMIT
            context['testcase_soft_limit'] = settings.VNOJ_TESTCASE_SOFT_LIMIT
        context['is_mirror_problem'] = self.object.is_mirror
        context['is_external_problem'] = self.object.has_external_problem
        mirror_form = context['mirror_form']
        if mirror_form.is_bound:
            context['test_source_mode'] = (
                mirror_form['test_source'].value() or ProblemMirrorForm.TEST_SOURCE_LOCAL
            )
        else:
            context['test_source_mode'] = mirror_form.initial.get(
                'test_source',
                ProblemMirrorForm.TEST_SOURCE_LOCAL,
            )
        context['external_problem'] = getattr(self.object, 'external_problem', None)
        context['mirror_source'] = self.object.mirror_of
        context['mirror_root'] = self.object.mirror_root
        context['mirror_dependents_count'] = kwargs.get('mirror_dependents_count', 0)
        context['show_mirror_root_warning'] = kwargs.get('show_mirror_root_warning', False)
        context['uploaded_archive_name'] = kwargs.get('uploaded_archive_name', '')
        return context

    def _archive_change_requested(self):
        return 'problem-data-zipfile' in self.request.FILES or 'problem-data-zipfile-clear' in self.request.POST

    def check_valid(self, mirror_form, external_form, data_form, cases_formset):
        mirror_valid = mirror_form.is_valid()
        external_valid = external_form.is_valid()
        data_valid = data_form.is_valid()
        if not mirror_valid or not external_valid or not data_valid:
            return False

        test_source = mirror_form.cleaned_data.get('test_source')
        external_enabled = external_form.cleaned_data.get('enabled')
        if external_enabled != (test_source == ProblemMirrorForm.TEST_SOURCE_EXTERNAL):
            mirror_form.add_error('test_source', _('The selected test source could not be applied.'))
            return False

        if test_source != ProblemMirrorForm.TEST_SOURCE_LOCAL:
            return True
        if not cases_formset.is_valid():
            return False
        number_of_cases = cases_formset.total_form_count() - len(cases_formset.deleted_forms)
        if number_of_cases > settings.VNOJ_TESTCASE_HARD_LIMIT and \
           not self.request.user.has_perm('judge.create_mass_testcases'):
            error = ValidationError(
                _('Too many testcases, number of testcases must not exceed %s') % settings.VNOJ_TESTCASE_HARD_LIMIT,
                code='too_many_testcases',
            )
            cases_formset._non_form_errors.append(error)
            return False
        return True

    def post(self, request, *args, **kwargs):
        self.object = problem = self.get_object()
        previous_mirror_of_id = problem.mirror_of_id
        self._copy_cases_if_missing_from_root()
        mirror_form = self.get_mirror_form(post=True)
        mirror_valid = mirror_form.is_valid()
        desired_source = (
            mirror_form.cleaned_data.get('test_source')
            if mirror_valid else None
        )
        external_form = self.get_external_form(
            post=True,
            enabled_override=desired_source == ProblemMirrorForm.TEST_SOURCE_EXTERNAL,
        )
        data_form = self.get_data_form(post=True)
        valid_files = self.get_valid_files(data_form.instance, post=True)
        data_form.zip_valid = valid_files is not False
        cases_formset = self.get_case_formset(valid_files, post=True)
        archive_change_requested = self._archive_change_requested()
        uploaded_archive_name = (
            request.FILES.get('problem-data-zipfile').name
            if 'problem-data-zipfile' in request.FILES else ''
        )

        if archive_change_requested and mirror_valid and desired_source != ProblemMirrorForm.TEST_SOURCE_LOCAL:
            data_form.add_error(None, _(
                'Mirror or Virtual Judge problems cannot upload archives directly.',
            ))

        mirror_dependents_count = 0
        if archive_change_requested and desired_source == ProblemMirrorForm.TEST_SOURCE_LOCAL:
            mirror_dependents_count = Problem.objects.filter(mirror_root_id=problem.id).exclude(pk=problem.id).count()
            if mirror_dependents_count and request.POST.get('confirm_mirror_root_archive_update') != '1':
                data_form.add_error(
                    None,
                    _('This problem is mirrored by %(count)d other problem(s). '
                        'Please confirm before replacing the shared root archive.') % {
                        'count': mirror_dependents_count,
                    },
                )

        if self.check_valid(mirror_form, external_form, data_form, cases_formset):
            problem = mirror_form.save()
            mirror_changed = previous_mirror_of_id != problem.mirror_of_id

            data = data_form.save()
            external_problem = None
            if external_form.cleaned_data.get('enabled') or external_form.instance.pk:
                external_problem = external_form.save()
            if hasattr(problem, 'has_external_problem'):
                delattr(problem, 'has_external_problem')
            if hasattr(problem, 'is_external'):
                delattr(problem, 'is_external')

            if external_problem and external_problem.is_active:
                if previous_mirror_of_id and not problem.mirror_of_id:
                    ProblemTestCase.objects.filter(dataset=problem).delete()
                    data.zipfile = None
                    data.save(update_fields=['zipfile'])
                ProblemDataCompiler.generate(problem, data, problem.cases.none(), [])
                return HttpResponseRedirect(request.get_full_path())

            if previous_mirror_of_id and not problem.mirror_of_id and not archive_change_requested:
                ProblemTestCase.objects.filter(dataset=problem).delete()
                current_data, _created = ProblemData.objects.get_or_create(problem=problem)
                current_data.zipfile = None
                current_data.save(update_fields=['zipfile'])
                ProblemDataCompiler.generate(problem, current_data, problem.cases.none(), [])
                return HttpResponseRedirect(request.get_full_path())

            if mirror_changed and problem.mirror_of_id:
                ProblemTestCase.objects.filter(dataset=problem).delete()
                current_data, _created = ProblemData.objects.get_or_create(problem=problem)
                current_data.zipfile = None
                current_data.save(update_fields=['zipfile'])
                self.object = problem
                self._bootstrap_mirror_config_from_root()
                self._copy_cases_if_missing_from_root()
                return HttpResponseRedirect(request.get_full_path())

            if problem.is_mirror:
                sync_mirror_archive_for_problem(
                    problem,
                    bootstrap_cases_if_empty=mirror_changed,
                    heal_missing_files=True,
                    force_regenerate=True,
                )
                return HttpResponseRedirect(request.get_full_path())

            self._save_cases_formset(problem, cases_formset)

            if mirror_changed:
                problem.refresh_from_db()
            ProblemDataCompiler.generate(problem, data, problem.cases.order_by('order'), valid_files)
            return HttpResponseRedirect(request.get_full_path())
        return self.render_to_response(
            self.get_context_data(
                mirror_form=mirror_form,
                data_form=data_form, cases_formset=cases_formset,
                external_form=external_form,
                valid_files=valid_files,
                mirror_dependents_count=mirror_dependents_count,
                show_mirror_root_warning=bool(mirror_dependents_count),
                uploaded_archive_name=uploaded_archive_name,
            ),
        )

    put = post


@login_required
def problem_data_file(request, problem, path):
    object = get_object_or_404(Problem, code=problem)
    if not _can_download_problem_data(request.user, object):
        raise Http404()

    problem_dir = problem_data_storage.path(problem)
    if os.path.commonpath((problem_data_storage.path(os.path.join(problem, path)), problem_dir)) != problem_dir:
        raise Http404()

    response = HttpResponse()

    if hasattr(settings, 'DMOJ_PROBLEM_DATA_INTERNAL'):
        url_path = '%s/%s/%s' % (settings.DMOJ_PROBLEM_DATA_INTERNAL, problem, path)
    else:
        url_path = None

    try:
        add_file_response(request, response, url_path, os.path.join(problem, path), problem_data_storage)
    except IOError:
        raise Http404()

    response['Content-Type'] = 'application/octet-stream'
    return response


@login_required
def verify_external_problem(request, problem):
    problem_obj = get_object_or_404(Problem, code=problem)
    if not problem_obj.is_editable_by(request.user):
        raise Http404()
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': _('POST is required.')}, status=405)

    config_id = request.POST.get('config') or request.POST.get('config_id')
    oj = (request.POST.get('oj') or '').strip()
    problem_id = (request.POST.get('external_problem_id') or request.POST.get('problem_id') or '').strip()
    if not config_id or not oj or not problem_id:
        return JsonResponse({'ok': False, 'error': _('Config, OJ, and problem ID are required.')}, status=400)

    config = get_object_or_404(ExternalJudgeConfig, id=config_id, is_active=True)
    try:
        client = ExternalJudgeClient(config)
        metadata = client.get_problem(oj, problem_id)
    except ExternalJudgeError as exc:
        return JsonResponse({'ok': False, 'error': user_safe_message(exc)}, status=400)
    if not isinstance(metadata, dict):
        metadata = {}

    languages = _extract_external_languages(metadata)
    if not languages:
        try:
            for oj_info in client.get_ojs() or []:
                if str(oj_info.get('oj', '')).lower() == oj.lower():
                    languages = _extract_external_languages(oj_info)
                    break
        except ExternalJudgeError:
            languages = []
    qhhoj_languages = list(Language.objects.filter(include_in_problem=True).order_by('name', 'key'))
    suggestions = []
    for entry in languages:
        vjudge_name = entry.get('name') or entry.get('text') or entry.get('id') or ''
        suggestion = _suggest_language_key(vjudge_name, qhhoj_languages)
        suggestions.append({
            'id': str(entry.get('id') or entry.get('value') or ''),
            'name': vjudge_name,
            'suggested_qhhoj_key': suggestion,
        })

    return JsonResponse({
        'ok': True,
        'title': metadata.get('title') or metadata.get('name') or '',
        'oj': metadata.get('oj') or oj,
        'problemId': metadata.get('problemId') or problem_id,
        'languages': suggestions,
        'metadata': metadata,
    })


def _extract_external_languages(payload):
    if not isinstance(payload, dict):
        return []
    raw_languages = (
        payload.get('languages') or
        payload.get('languageMap') or
        payload.get('language_map') or
        []
    )
    if isinstance(raw_languages, dict):
        normalized = []
        for key, value in raw_languages.items():
            key = str(key)
            value = str(value)
            if key.isdigit() or not value.isdigit():
                normalized.append({'id': key, 'name': value})
            else:
                normalized.append({'id': value, 'name': key})
        return normalized
    if isinstance(raw_languages, list):
        normalized = []
        for entry in raw_languages:
            if isinstance(entry, dict):
                normalized.append(entry)
            elif entry:
                normalized.append({'id': str(entry), 'name': str(entry)})
        return normalized
    return []


def _suggest_language_key(vjudge_name, languages):
    normalized = _normalize_language_name(vjudge_name)
    if not normalized:
        return ''
    best_key = ''
    best_score = 0
    for language in languages:
        candidates = [language.key, language.name, language.common_name, language.short_name]
        for candidate in candidates:
            score = _language_match_score(normalized, _normalize_language_name(candidate))
            if score > best_score:
                best_score = score
                best_key = language.key
    return best_key if best_score >= 55 else ''


def _normalize_language_name(value):
    value = (value or '').lower()
    aliases = {
        'gnu g++': 'cpp',
        'g++': 'cpp',
        'c++': 'cpp',
        'python 3': 'python3',
        'pypy 3': 'pypy3',
    }
    for old, new in aliases.items():
        value = value.replace(old, new)
    return ''.join(ch for ch in value if ch.isalnum())


def _language_match_score(left, right):
    if not left or not right:
        return 0
    if left == right:
        return 100
    if left in right or right in left:
        return 75
    common = len(set(left) & set(right))
    return int(common / max(len(set(left)), len(set(right))) * 60)


@login_required
def problem_init_view(request, problem):
    problem = get_object_or_404(Problem, code=problem)
    if not _can_download_problem_data(request.user, problem):
        raise Http404()

    try:
        with problem_data_storage.open(os.path.join(problem.code, 'init.yml'), 'rb') as f:
            data = utf8text(f.read()).rstrip('\n')
    except IOError:
        raise Http404()

    return render(
        request, 'problem/yaml.html', {
            'raw_source': data, 'highlighted_source': highlight_code(data, 'yaml'),
            'title': _('Generated init.yml for %s') % problem.name,
            'content_title': mark_safe(
                escape(_('Generated init.yml for %s')) % (
                    format_html(
                        '<a href="{1}">{0}</a>', problem.name,
                        reverse('problem_detail', args=[problem.code]),
                    )
                ),
            ),
        },
    )
