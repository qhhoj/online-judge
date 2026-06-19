import logging
import re
import uuid

from django.utils import timezone
from django.utils.translation import gettext as _

from judge import event_poster as event
from judge.models import ExternalSubmission, Submission, SubmissionTestCase
from judge.utils.external_judge_client import ExternalJudgeClient, ExternalJudgeError, user_safe_message


logger = logging.getLogger('judge.external_judge')


EXTERNAL_REJECTED_STATUS = 'rejected'
SELECTED_LANGUAGE_RESPONSE_KEY = '_qhhoj_selected_external_language'

STATUS_MAP = {
    'AC': ('D', 'AC'),
    'WA': ('D', 'WA'),
    'TLE': ('D', 'TLE'),
    'TIMEOUT': ('D', 'TLE'),
    'MLE': ('D', 'MLE'),
    'RE': ('D', 'RTE'),
    'RTE': ('D', 'RTE'),
    'IR': ('D', 'IR'),
    'CE': ('CE', 'CE'),
    'IE': ('IE', 'IE'),
    'OLE': ('D', 'OLE'),
    'PE': ('D', 'WA'),
}

PROCESSING_STATUS_CANONICALS = {
    'PENDING',
    'QUEUED',
    'POLLING',
    'PROCESSING',
    'RUNNING',
    'SUBMITTING',
}

PROCESSING_SYSTEM_STATUSES = {
    'pending',
    'queued',
    'polling',
    'processing',
    'running',
    'submitting',
}


def get_language_mapping(external_problem, language):
    return external_problem.get_language_mapping(language)


def mapping_vjudge_id(mapping):
    if not isinstance(mapping, dict):
        return None
    return mapping.get('vjudge_id') or mapping.get('vjudge_language_id') or mapping.get('language')


def selected_external_language_mapping(submission, external_problem, ext_sub=None):
    mapping = getattr(submission, '_external_language_mapping', None)
    if mapping_vjudge_id(mapping):
        return mapping

    raw_response = getattr(ext_sub, 'raw_response', None) if ext_sub is not None else None
    if isinstance(raw_response, dict):
        mapping = raw_response.get(SELECTED_LANGUAGE_RESPONSE_KEY)
        if mapping_vjudge_id(mapping):
            return mapping

    return get_language_mapping(external_problem, submission.language)


def raw_response_with_selected_language(raw_response, mapping):
    data = raw_response.copy() if isinstance(raw_response, dict) else {}
    if mapping_vjudge_id(mapping):
        data[SELECTED_LANGUAGE_RESPONSE_KEY] = {
            'qhhoj_key': mapping.get('qhhoj_key') or '',
            'vjudge_id': mapping_vjudge_id(mapping),
            'vjudge_name': mapping.get('vjudge_name') or '',
        }
    return data


def external_submission_is_rejected(submission, ext_sub):
    return submission.result == 'RJ' or ext_sub.pcd_system_status == EXTERNAL_REJECTED_STATUS


def _status_token(value, *, upper=True):
    token = re.sub(r'[\s-]+', '_', str(value or '').strip())
    return token.upper() if upper else token.lower()


def _external_system_status(data):
    if not isinstance(data, dict):
        return ''
    return _status_token(data.get('systemStatus') or data.get('status'), upper=False)


def get_external_status_canonical(data):
    if not isinstance(data, dict):
        return ''
    raw_status = data.get('rawVjudgeStatus') or {}
    if not isinstance(raw_status, dict):
        raw_status = {}
    status = (
        data.get('statusCanonical') or
        data.get('vjudgeStatusCanonical') or
        raw_status.get('statusCanonical') or
        raw_status.get('vjudgeStatusCanonical')
    )
    return _status_token(status)


def external_result_is_processing(data):
    status_canonical = get_external_status_canonical(data)
    system_status = _external_system_status(data)
    processing = data.get('processing') if isinstance(data, dict) else None
    return (
        processing is True or
        status_canonical in PROCESSING_STATUS_CANONICALS or
        system_status in PROCESSING_SYSTEM_STATUSES
    )


def external_result_is_submit_failed(data):
    status_canonical = get_external_status_canonical(data)
    system_status = _external_system_status(data)
    return (
        status_canonical.startswith('SUBMIT_FAILED') or
        system_status.startswith('submit_failed')
    )


def external_error_message(data, default=None):
    if not isinstance(data, dict):
        return default
    message = data.get('errorMessage')
    if message is None:
        return default
    message = str(message).strip()
    return message or default


def get_external_score_text(data):
    if not isinstance(data, dict):
        return None
    raw_status = data.get('rawVjudgeStatus') or {}
    if not isinstance(raw_status, dict):
        raw_status = {}
    return (
        data.get('scoreText') or
        data.get('vjudgeScoreText') or
        raw_status.get('scoreText') or
        raw_status.get('vjudgeScoreText')
    )


def set_external_submission_error(submission, message, *, result='IE'):
    status = 'CE' if result == 'CE' else 'IE'
    Submission.objects.filter(id=submission.id).update(
        status=status,
        result=result,
        points=0,
        case_points=0,
        case_total=submission.problem.points,
        error=message,
        judged_date=timezone.now(),
    )
    submission.refresh_from_db()
    _finish_submission_updates(submission)


def _start_external_submission(submission):
    Submission.objects.filter(id=submission.id).update(status='P', judged_date=timezone.now())
    submission.refresh_from_db()
    event.post('sub_%s' % submission.id_secret, {'type': 'grading-begin'})
    from judge.judgeapi import _post_update_submission
    _post_update_submission(submission)


def schedule_external_submission(submission, rejudge=False, batch_rejudge=False):
    # Refresh to get latest state (judge_submission may have already reset status to QU)
    submission.refresh_from_db()

    try:
        external_problem = submission.problem.external_problem
    except Exception:
        set_external_submission_error(submission, _('Bài này chưa được cấu hình external judge.'))
        return False

    if not external_problem.is_active:
        set_external_submission_error(submission, _('Bài này tạm thời không nhận submission'))
        return False
    if not external_problem.config_id or not external_problem.config or not external_problem.config.is_active:
        set_external_submission_error(submission, _('Bài này tạm thời không nhận submission'))
        return False

    try:
        existing_ext_sub = submission.external_submission
    except ExternalSubmission.DoesNotExist:
        existing_ext_sub = None
    mapping = selected_external_language_mapping(submission, external_problem, existing_ext_sub)
    vjudge_language_id = mapping_vjudge_id(mapping or {})
    if not vjudge_language_id:
        set_external_submission_error(
            submission,
            _('Ngôn ngữ %(language)s chưa được hỗ trợ cho bài này') % {
                'language': submission.language.name,
            },
            result='CE',
        )
        return False

    _start_external_submission(submission)

    if rejudge or batch_rejudge:
        ExternalSubmission.objects.filter(submission=submission).delete()

    expected_pcd_submission_id = uuid.uuid4()
    ExternalSubmission.objects.update_or_create(
        submission=submission,
        defaults={
            'config': external_problem.config,
            'pcd_submission_id': expected_pcd_submission_id,
            'pcd_system_status': 'queued',
            'pcd_status_canonical': None,
            'pcd_vjudge_run_id': None,
            'pcd_remote_url': None,
            'pcd_runtime_ms': None,
            'pcd_memory_kb': None,
            'pcd_score_text': None,
            'last_polled_at': None,
            'poll_attempts': 0,
            'raw_response': raw_response_with_selected_language({}, mapping),
        },
    )

    from judge.tasks.external_judge import submit_external_submission
    try:
        submit_external_submission.apply_async(
            args=[submission.id, rejudge, batch_rejudge, str(expected_pcd_submission_id)],
        )
    except Exception:
        logger.exception(
            'Failed to enqueue external submission task: submission_id=%s rejudge=%s batch_rejudge=%s',
            submission.id,
            rejudge,
            batch_rejudge,
        )
        set_external_submission_error(
            submission,
            _('Không thể đưa bài lên hàng đợi đánh giá external judge. Vui lòng thử lại sau.'),
        )
        return False

    return True


def perform_external_submission(submission, rejudge=False, batch_rejudge=False, expected_pcd_submission_id=None):
    # Refresh to get latest state (submission object may be stale in async task workers)
    submission.refresh_from_db()

    try:
        external_problem = submission.problem.external_problem
    except Exception:
        set_external_submission_error(submission, _('Bài này chưa được cấu hình external judge.'))
        return False

    if not external_problem.is_active:
        set_external_submission_error(submission, _('Bài này tạm thời không nhận submission'))
        return False
    if not external_problem.config_id or not external_problem.config or not external_problem.config.is_active:
        set_external_submission_error(submission, _('Bài này tạm thời không nhận submission'))
        return False

    ext_sub_filter = {'submission': submission}
    if expected_pcd_submission_id is not None:
        ext_sub_filter['pcd_submission_id'] = expected_pcd_submission_id

    if not ExternalSubmission.objects.filter(**ext_sub_filter).exists():
        logger.info(
            'Ignoring stale external submit task: submission_id=%s expected_pcd_submission_id=%s',
            submission.id,
            expected_pcd_submission_id,
        )
        return False

    ext_sub = ExternalSubmission.objects.filter(**ext_sub_filter).first()
    if ext_sub is None:
        return False

    mapping = selected_external_language_mapping(submission, external_problem, ext_sub)
    vjudge_language_id = mapping_vjudge_id(mapping or {})
    if not vjudge_language_id:
        set_external_submission_error(
            submission,
            _('Ngôn ngữ %(language)s chưa được hỗ trợ cho bài này') % {
                'language': submission.language.name,
            },
            result='CE',
        )
        return False

    if submission.status != 'P':
        _start_external_submission(submission)

    source = submission.source.source
    try:
        client = ExternalJudgeClient(external_problem.config)
        response = client.submit(
            oj=external_problem.oj,
            problem_id=external_problem.external_problem_id,
            language=vjudge_language_id,
            source=source,
            open=True,
        )
    except ExternalJudgeError as exc:
        logger.warning(  # noqa: G200
            'External submit failed: config=%s submission_id=%s status=%s error=%s',
            getattr(external_problem.config, 'name', '<unknown>'),
            submission.id,
            getattr(exc, 'status_code', None),
            exc,
        )
        set_external_submission_error(submission, user_safe_message(exc))
        return False

    pcd_submission_id = response.get('submissionId')
    system_status = response.get('systemStatus') or response.get('status') or 'pending'
    if external_result_is_submit_failed(response) or not pcd_submission_id:
        ext_sub.pcd_system_status = system_status
        ext_sub.pcd_status_canonical = get_external_status_canonical(response) or None
        ext_sub.raw_response = raw_response_with_selected_language(response, mapping)
        ext_sub.save(update_fields=['pcd_system_status', 'pcd_status_canonical', 'raw_response', 'updated_at'])
        error_msg = external_error_message(response, _('External judge từ chối submission này'))
        set_external_submission_error(submission, error_msg)
        return False

    try:
        pcd_submission_id = uuid.UUID(str(pcd_submission_id))
    except (TypeError, ValueError):
        set_external_submission_error(
            submission,
            _('External judge trả về submissionId không hợp lệ.'),
        )
        return False

    update_filter = {'id': ext_sub.id}
    if expected_pcd_submission_id is not None:
        update_filter['pcd_submission_id'] = expected_pcd_submission_id

    updated = ExternalSubmission.objects.filter(**update_filter).update(
        config=external_problem.config,
        pcd_submission_id=pcd_submission_id,
        pcd_system_status=system_status,
        pcd_status_canonical=get_external_status_canonical(response) or None,
        pcd_vjudge_run_id=response.get('vjudgeRunId'),
        pcd_remote_url=response.get('remoteUrl') or None,
        pcd_runtime_ms=response.get('runtimeMs'),
        pcd_memory_kb=response.get('memoryKb'),
        pcd_score_text=get_external_score_text(response),
        last_polled_at=None,
        poll_attempts=0,
        raw_response=raw_response_with_selected_language(response, mapping),
        updated_at=timezone.now(),
    )

    if not updated:
        logger.info(
            'Ignoring stale external submit result: submission_id=%s expected_pcd_submission_id=%s actual=%s',
            submission.id,
            expected_pcd_submission_id,
            pcd_submission_id,
        )
        return False

    ext_sub = ExternalSubmission.objects.select_related('submission', 'config').get(id=ext_sub.id)

    from judge.tasks.external_judge import poll_external_submission
    poll_external_submission.apply_async(
        args=[submission.id, str(pcd_submission_id)],
        countdown=external_problem.config.poll_interval_seconds,
    )

    if submission.status == 'P' and ext_sub:
        from judge.judgeapi import _post_update_submission
        _post_update_submission(submission)
    return True


def handle_external_submission(submission, rejudge=False, batch_rejudge=False):
    return schedule_external_submission(submission, rejudge=rejudge, batch_rejudge=batch_rejudge)


def reject_external_submission(submission):
    ExternalSubmission.objects.filter(submission=submission).update(
        pcd_system_status=EXTERNAL_REJECTED_STATUS,
        pcd_status_canonical='RJ',
        last_polled_at=timezone.now(),
    )
    Submission.objects.filter(id=submission.id).update(
        status='D',
        result='RJ',
        points=0,
        case_points=0,
        case_total=submission.problem.points,
        error=_('Submission rejected by admin. External judge polling stopped.'),
        judged_date=timezone.now(),
    )
    SubmissionTestCase.objects.filter(submission=submission).update(
        status='RJ',
        points=0,
        feedback='',
        extended_feedback='',
        time=0,
        memory=0,
    )
    submission.refresh_from_db()
    _finish_submission_updates(submission)


def parse_score_percent(score_text):
    if score_text is None:
        return None
    text = str(score_text).strip()
    if not text:
        return None
    fraction = re.search(r'(-?\d+(?:\.\d+)?)\s*/\s*(-?\d+(?:\.\d+)?)', text)
    try:
        if fraction:
            value = float(fraction.group(1))
            total = float(fraction.group(2))
            if total <= 0:
                return None
            return max(0.0, min(100.0, value / total * 100.0))
        number = re.search(r'-?\d+(?:\.\d+)?', text)
        if not number:
            return None
        return max(0.0, min(100.0, float(number.group(0))))
    except (TypeError, ValueError):
        return None


def finalize_external_submission(submission, ext_sub, data):
    status_canonical = get_external_status_canonical(data)
    error_message = external_error_message(data)

    if external_result_is_submit_failed(data):
        status, result = 'IE', 'IE'
        error_message = error_message or _('External judge từ chối submission này')
    elif external_result_is_processing(data):
        logger.warning(
            'External finalize received non-final status: submission_id=%s system_status=%s canonical=%s',
            submission.id,
            _external_system_status(data),
            status_canonical or None,
        )
        return False
    elif status_canonical in STATUS_MAP:
        status, result = STATUS_MAP[status_canonical]
    elif error_message:
        logger.warning(
            'External finalize falling back to IE from errorMessage: submission_id=%s system_status=%s canonical=%s',
            submission.id,
            _external_system_status(data),
            status_canonical or None,
        )
        status, result = 'IE', 'IE'
    else:
        logger.warning(
            'External finalize received unsupported final status: submission_id=%s system_status=%s canonical=%s',
            submission.id,
            _external_system_status(data),
            status_canonical or None,
        )
        status, result = 'IE', 'IE'
        error_message = _('External judge trả về trạng thái không được hỗ trợ.')
    problem = submission.problem

    score_text = get_external_score_text(data)
    score_percent = parse_score_percent(score_text)

    if result == 'AC' or (score_percent is not None and score_percent >= 100.0):
        status = 'D'
        result = 'AC'
        case_points = problem.points
    elif score_percent is not None and problem.partial:
        if status in ('IE', 'CE'):
            status = 'D'
            result = 'WA'
        case_points = round(score_percent / 100.0 * problem.points, 3)
        if case_points >= problem.points:
            status = 'D'
            result = 'AC'
    else:
        case_points = 0
    case_total = problem.points
    points = case_points
    if not problem.partial and points < problem.points:
        points = 0

    runtime_ms = data.get('runtimeMs')
    memory_kb = data.get('memoryKb')

    # Update ExternalSubmission score text for display
    if score_text and score_text != ext_sub.pcd_score_text:
        ext_sub.pcd_score_text = score_text
        ext_sub.save(update_fields=['pcd_score_text', 'updated_at'])

    Submission.objects.filter(id=submission.id).update(
        status=status,
        result=result,
        case_points=case_points,
        case_total=case_total,
        points=points,
        time=(runtime_ms / 1000.0) if runtime_ms is not None else None,
        memory=memory_kb,
        error=error_message if status in ('IE', 'CE') else None,
        judged_date=timezone.now(),
    )
    SubmissionTestCase.objects.filter(submission=submission).delete()
    submission.refresh_from_db()
    _finish_submission_updates(submission)
    return True


def _finish_submission_updates(submission):
    from judge.caching import finished_submission
    from judge.judgeapi import _post_update_submission

    if submission.problem.is_public and not submission.problem.is_organization_private:
        submission.user._updating_stats_only = True
        submission.user.calculate_points()

    submission.problem._updating_stats_only = True
    submission.problem.update_stats()
    submission.update_contest()
    finished_submission(submission)
    _post_update_submission(submission, done=True)
    event.post('sub_%s' % submission.id_secret, {'type': 'grading-end'})
