import logging

from celery import shared_task
from django.utils import timezone
from django.utils.translation import gettext as _

from judge.external_judge import (
    perform_external_submission,
    external_result_is_processing,
    external_submission_is_rejected,
    finalize_external_submission,
    get_external_score_text,
    get_external_status_canonical,
    raw_response_with_selected_language,
    set_external_submission_error,
    selected_external_language_mapping,
)
from judge.models import ExternalSubmission, Submission
from judge.utils.external_judge_client import (
    ExternalJudgeAuthError,
    ExternalJudgeBadRequestError,
    ExternalJudgeClient,
    ExternalJudgeConfigurationError,
    ExternalJudgeError,
    user_safe_message,
)


logger = logging.getLogger('judge.external_judge')

# Maximum time (in seconds) a poll task can run before auto-timeout
EXTERNAL_POLL_HARD_TIMEOUT_SECONDS = 30 * 60  # 30 minutes

NON_RETRYABLE_POLL_ERRORS = (
    ExternalJudgeAuthError,
    ExternalJudgeBadRequestError,
    ExternalJudgeConfigurationError,
)


def _mark_external_poll_error(ext_sub, submission, message):
    set_external_submission_error(submission, message)
    ExternalSubmission.objects.filter(id=ext_sub.id).update(
        pcd_system_status='config_error',
        last_polled_at=timezone.now(),
        updated_at=timezone.now(),
    )


@shared_task(bind=True, max_retries=None)
def submit_external_submission(self, submission_id, rejudge=False, batch_rejudge=False, expected_pcd_submission_id=None):
    try:
        submission = Submission.objects.select_related(
            'problem',
            'problem__external_problem',
            'language',
            'source',
        ).get(id=submission_id)
    except Submission.DoesNotExist:
        return

    return perform_external_submission(
        submission,
        rejudge=rejudge,
        batch_rejudge=batch_rejudge,
        expected_pcd_submission_id=expected_pcd_submission_id,
    )


@shared_task(bind=True, max_retries=None)
def poll_external_submission(self, submission_id, expected_pcd_submission_id=None):
    try:
        ext_sub = ExternalSubmission.objects.select_related(
            'submission',
            'submission__problem',
            'submission__user',
            'submission__language',
            'config',
        ).get(submission_id=submission_id)
    except ExternalSubmission.DoesNotExist:
        return

    if expected_pcd_submission_id and str(ext_sub.pcd_submission_id) != str(expected_pcd_submission_id):
        logger.info('Ignoring stale external poll task: submission_id=%s', submission_id)
        return

    submission = ext_sub.submission
    if external_submission_is_rejected(submission, ext_sub):
        return
    if submission.status in ('D', 'CE', 'IE', 'AB', 'RJ') and not ext_sub.pcd_system_status in ('queued', 'polling'):
        return

    config = ext_sub.config
    if not config or not config.is_active:
        _mark_external_poll_error(ext_sub, submission, _('Bài này tạm thời không nhận submission'))
        return

    # Hard timeout: if submission has been polling for more than 30 minutes, give up
    if ext_sub.created_at and (timezone.now() - ext_sub.created_at).total_seconds() > EXTERNAL_POLL_HARD_TIMEOUT_SECONDS:
        set_external_submission_error(
            submission,
            _('Không nhận được kết quả từ external judge sau thời gian chờ (timeout 30 phút)')
        )
        ext_sub.pcd_system_status = 'poll_timeout'
        ext_sub.save(update_fields=['pcd_system_status', 'updated_at'])
        return

    ext_sub.poll_attempts += 1
    ext_sub.last_polled_at = timezone.now()
    ext_sub.save(update_fields=['poll_attempts', 'last_polled_at', 'updated_at'])

    if ext_sub.poll_attempts > config.max_poll_attempts:
        # Fallback: also check attempt count as safety net
        set_external_submission_error(submission, _('Không nhận được kết quả từ external judge sau thời gian chờ'))
        ext_sub.pcd_system_status = 'poll_timeout'
        ext_sub.save(update_fields=['pcd_system_status', 'updated_at'])
        return

    try:
        client = ExternalJudgeClient(config, timeout=config.poll_timeout_seconds)
        data = client.get_submission_status(str(ext_sub.pcd_submission_id))
    except NON_RETRYABLE_POLL_ERRORS as exc:
        logger.warning(
            'External poll failed with non-retryable error: config=%s submission_id=%s status=%s attempt=%s error=%s',
            getattr(config, 'name', '<unknown>'),
            submission.id,
            getattr(exc, 'status_code', None),
            ext_sub.poll_attempts,
            exc,
        )
        _mark_external_poll_error(ext_sub, submission, user_safe_message(exc))
        return
    except ExternalJudgeError as exc:
        logger.warning(
            'External poll failed: config=%s submission_id=%s status=%s attempt=%s error=%s',
            getattr(config, 'name', '<unknown>'),
            submission.id,
            getattr(exc, 'status_code', None),
            ext_sub.poll_attempts,
            exc,
        )
        delay = min(config.poll_interval_seconds * (1.5 ** min(ext_sub.poll_attempts, 5)), 30)
        raise self.retry(countdown=delay)

    submission.refresh_from_db(fields=['result'])
    ext_sub.refresh_from_db(fields=['pcd_system_status'])
    if external_submission_is_rejected(submission, ext_sub):
        return

    ext_sub.pcd_system_status = data.get('systemStatus', ext_sub.pcd_system_status)
    ext_sub.pcd_status_canonical = get_external_status_canonical(data) or None
    ext_sub.pcd_runtime_ms = data.get('runtimeMs')
    ext_sub.pcd_memory_kb = data.get('memoryKb')
    ext_sub.pcd_score_text = get_external_score_text(data) or ext_sub.pcd_score_text
    ext_sub.pcd_remote_url = data.get('remoteUrl') or None
    ext_sub.pcd_vjudge_run_id = data.get('vjudgeRunId') or ext_sub.pcd_vjudge_run_id
    ext_sub.raw_response = raw_response_with_selected_language(
        data,
        selected_external_language_mapping(submission, submission.problem.external_problem, ext_sub),
    )
    ext_sub.save()

    # Only finalize when the external judge reports a conclusive, non-processing
    # result. A missing/None `processing` value or a still-queued/polling
    # `systemStatus` means the remote judging is not finished yet — keep
    # polling instead of finalizing prematurely (which would map an empty
    # status canonical to IE). The hard timeout / max_poll_attempts above bound
    # the retry loop.
    system_status = (data.get('systemStatus') or '').lower()
    still_processing = data.get('processing') is not False
    if still_processing or system_status in ('', 'queued', 'polling', 'submitting') or external_result_is_processing(data):
        raise self.retry(countdown=config.poll_interval_seconds)

    if not finalize_external_submission(submission, ext_sub, data):
        raise self.retry(countdown=config.poll_interval_seconds)
