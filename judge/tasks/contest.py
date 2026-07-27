import fnmatch
import json
import os
import re
import zipfile

from celery import shared_task
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import default_storage
from django.utils.translation import gettext as _
from mosspy import Moss as MOSS

from judge.models import (
    Contest,
    ContestMoss,
    ContestParticipation,
    ContestSubmission,
    Problem,
    Submission,
)
from judge.utils.celery import Progress


__all__ = (
    'rescore_contest',
    'run_moss',
    'prepare_contest_data',
    'judge_final_submissions',
    'check_final_submission_contests',
)
rewildcard = re.compile(r'\*+')


@shared_task(bind=True)
def rescore_contest(self, contest_key):
    contest = Contest.objects.get(key=contest_key)
    participations = contest.users

    rescored = 0
    with Progress(self, participations.count(), stage=_('Recalculating contest scores')) as p:
        for participation in participations.iterator():
            participation.recompute_results()
            rescored += 1
            if rescored % 10 == 0:
                p.done = rescored
    return rescored


MOSS_IGNORE = {
    'CE',
    'IE',
    'AB',
    'RJ',
}


@shared_task(bind=True)
def run_moss(self, contest_key):
    moss_api_key = settings.MOSS_API_KEY
    if moss_api_key is None:
        raise ImproperlyConfigured('No MOSS API Key supplied')

    contest = Contest.objects.get(key=contest_key)
    ContestMoss.objects.filter(contest=contest).delete()

    length = len(ContestMoss.LANG_MAPPING) * contest.problems.count()
    moss_results = []

    with Progress(self, length, stage=_('Running MOSS')) as p:
        for problem in contest.problems.all():
            for dmoj_lang, moss_lang in ContestMoss.LANG_MAPPING:
                result = ContestMoss(contest=contest, problem=problem, language=dmoj_lang)

                subs = Submission.objects.filter(
                    contest__participation__virtual__in=(ContestParticipation.LIVE, ContestParticipation.SPECTATE),
                    contest_object=contest,
                    problem=problem,
                    language__common_name=dmoj_lang,
                ).order_by('-points').values_list(
                    'user__user__username',
                    'source__source',
                ).exclude(result__in=MOSS_IGNORE).exclude(
                    case_points=0,
                ).order_by('-points').values_list(
                    'user__user__username',
                    'source__source',
                    'id',
                )

                if subs.exists():
                    moss_call = MOSS(
                        moss_api_key, language=moss_lang, matching_file_limit=100,
                        comment='%s - %s' % (contest.key, problem.code),
                    )

                    users = set()

                    for username, source, sub_id in subs:
                        if username in users:
                            continue
                        users.add(username)
                        moss_call.add_file_from_memory(
                            username,
                            (
                                '// ' + settings.SITE_FULL_URL +
                                '/submission/' + str(sub_id) +
                                '\n' + source
                            ).encode('utf-8'),
                        )

                    result.url = moss_call.process()
                    result.submission_count = len(users)

                moss_results.append(result)
                p.did(1)

    ContestMoss.objects.bulk_create(moss_results)

    return len(moss_results)


@shared_task(bind=True)
def prepare_contest_data(self, contest_id, options):
    options = json.loads(options)

    with Progress(self, 1, stage=_('Applying filters')) as p:
        # Force an update so that we get a progress bar.
        p.done = 0
        contest = Contest.objects.get(id=contest_id)
        queryset = ContestSubmission.objects.filter(participation__contest=contest, participation__virtual=0) \
                                    .order_by('-points', 'id') \
                                    .select_related(
                                        'problem__problem', 'submission__user__user',
                                        'submission__source', 'submission__language',
        ) \
            .values_list(
                                        'submission__user__user__id', 'submission__user__user__username',
                                        'problem__problem__code', 'submission__source__source',
                                        'submission__language__extension', 'submission__id',
                                        'submission__language__file_only',
        )

        if options['submission_results']:
            queryset = queryset.filter(result__in=options['submission_results'])

        # Compress wildcards to avoid exponential complexity on certain glob patterns before Python 3.9.
        # For details, see <https://bugs.python.org/issue40480>.
        problem_glob = rewildcard.sub('*', options['submission_problem_glob'])
        if problem_glob != '*':
            queryset = queryset.filter(
                problem__problem__in=Problem.objects.filter(code__regex=fnmatch.translate(problem_glob)),
            )

        submissions = list(queryset)
        p.did(1)

    length = len(submissions)
    with Progress(self, length, stage=_('Preparing contest data')) as p:
        data_file = zipfile.ZipFile(os.path.join(settings.DMOJ_CONTEST_DATA_CACHE, '%s.zip' % contest_id), mode='w')
        exported = set()
        for user_id, username, problem, source, ext, sub_id, file_only in submissions:
            if (user_id, problem) in exported:
                path = os.path.join(username, '$History', f'{problem}_{sub_id}.{ext}')
            else:
                path = os.path.join(username, f'{problem}.{ext}')
                exported.add((user_id, problem))

            if file_only:
                # Get the basename of the source as it is an URL
                filename = os.path.basename(source)
                data_file.write(
                    default_storage.path(
                        os.path.join(
                            settings.SUBMISSION_FILE_UPLOAD_MEDIA_DIR,
                            problem, str(user_id), filename,
                        ),
                    ),
                    path,
                )
                pass
            else:
                data_file.writestr(path, source)

            p.did(1)

        data_file.close()

    return length


# Submissions that automatic judging is allowed to touch: the ones the FSO flow parked while the
# contest was running ('PD'), and ones that failed with an internal error ('IE').
#
# Deliberately absent:
#   'D'      a finished submission must never be reset by an automatic trigger, or repeated triggers
#            destroy and regenerate test case results for the whole contest.
#   'QU'     already queued and dispatched; re-dispatching is redundant, and including it would mean
#            two runs in a row do not settle. Excluding it is what makes this selection idempotent:
#            every status this set touches moves to 'QU', which the set does not match.
#   'P','G'  currently on a judge.
#
# A submission genuinely stranded in 'QU' (dispatch failed) therefore needs an explicit rejudge --
# the contest's Judge Submissions button, or `manage.py check_fso_contests --force --rejudge-all`.
FSO_UNJUDGED_STATUSES = ('PD', 'IE')


def _judge_final_submissions_impl(contest_key, rejudge_all=False, progress_callback=None):
    """
    Implementation of judging logic for FSO contests.
    Can be called directly (synchronous) or from Celery task (asynchronous).

    Args:
        contest_key: Contest key
        rejudge_all: If True, reset and rejudge every submission in the contest (except ones being
            graded right now). This is destructive and is only appropriate for an explicit,
            operator-initiated rejudge.
            If False (the default, and what every automatic trigger passes), only submissions that
            have not been judged yet are picked up, which makes this function idempotent.
        progress_callback: Optional callback function(current, total, percent) for progress updates

    Returns:
        dict with status, counts, and message
    """
    from django.utils import timezone
    from judge.models import SubmissionTestCase
    import logging

    logger = logging.getLogger('judge.tasks.contest')
    logger.info('=== judge_final_submissions started for %s, rejudge_all=%s ===', contest_key, rejudge_all)

    contest = Contest.objects.get(key=contest_key)

    # Verify this is a final_submission format contest
    if contest.format_name != 'final_submission':
        return {
            'status': 'error',
            'message': 'Not a Final Submission Only contest',
            'contest_key': contest_key,
        }

    submissions = Submission.objects.filter(contest__participation__contest=contest)
    if rejudge_all:
        # Explicit operator rejudge: everything except what is on a judge right now.
        submissions = submissions.exclude(status__in=('P', 'G'))
    else:
        submissions = submissions.filter(status__in=FSO_UNJUDGED_STATUSES)

    # Snapshot the ids up front. Everything below works off this list rather than re-evaluating the
    # queryset, whose filter is on the very column the bulk update rewrites.
    submission_ids = list(submissions.values_list('id', flat=True))
    total_submissions = len(submission_ids)
    logger.info('Submissions to queue: %s', total_submissions)

    # Report progress if callback provided
    if progress_callback:
        progress_callback(0, total_submissions, 0)

    if total_submissions == 0:
        logger.info('No submissions to queue')
        return {
            'status': 'completed',
            'contest_key': contest_key,
            'queued_count': 0,
            'total': 0,
            'message': 'No submissions to queue',
        }

    # Delete old test cases for all submissions (to ensure clean rejudge)
    deleted_count = SubmissionTestCase.objects.filter(submission_id__in=submission_ids).delete()[0]
    logger.info('Deleted %s old test cases', deleted_count)

    # Bulk update all submissions to Queued status
    # This is MUCH faster than calling judge_submission() for each one
    update_fields = {
        'time': None,
        'memory': None,
        'points': None,
        'result': None,
        'case_points': 0,
        'case_total': 0,
        'error': None,
        'status': 'QU',  # Queued - judge server will pick up automatically
        'rejudged_date': timezone.now(),  # Always set rejudged_date
    }

    # Bulk update in one query - instant!
    queued_count = Submission.objects.filter(id__in=submission_ids).update(**update_fields)
    logger.info('✓ Bulk updated %s submissions to QU status', queued_count)

    # Now dispatch all submissions to judge server
    # Get fresh submission objects after update
    from judge.judgeapi import judge_submission

    logger.info('Dispatching submissions to judge server...')
    dispatched = 0
    failed = 0

    # Dispatch in batches to avoid overwhelming the system
    for submission_id in submission_ids:
        try:
            submission = Submission.objects.select_related('problem', 'language', 'source').get(id=submission_id)
            # Call judge_submission with batch_rejudge=True
            # This will dispatch to bridge without changing status (already QU)
            if judge_submission(submission, rejudge=True, batch_rejudge=True):
                dispatched += 1
            else:
                failed += 1
        except Exception:
            logger.exception('Failed to dispatch submission %s', submission_id)
            failed += 1

    logger.info('✓ Dispatched %s submissions to judge server (%s failed)', dispatched, failed)

    # Report final progress
    if progress_callback:
        progress_callback(queued_count, total_submissions, 100)

    # Note: Auto-rescore is handled by judge_handler.py after each submission is graded
    # No need to schedule rescore here as it will be triggered automatically

    logger.info('=== judge_final_submissions completed for %s ===', contest_key)

    return {
        'status': 'completed',
        'contest_key': contest_key,
        'queued_count': queued_count,
        'dispatched_count': dispatched,
        'failed_count': failed,
        'total': total_submissions,
        'message': (
            f'Queued {queued_count} submissions, dispatched {dispatched} to judge server. '
            'Auto-rescore will trigger after grading.'
        ),
    }


@shared_task(bind=True)
def judge_final_submissions(self, contest_key, rejudge_all=False):
    """
    Celery task wrapper for judging FSO contest submissions.
    Reports progress via Celery task state.
    """
    def progress_callback(current, total, percent):
        self.update_state(
            state='PROGRESS',
            meta={
                'current': current,
                'total': total,
                'percent': percent,
                'contest_key': contest_key,
                'status': 'judging',
            },
        )

    return _judge_final_submissions_impl(contest_key, rejudge_all, progress_callback)


@shared_task(bind=True)
def check_final_submission_contests(self):
    """
    Periodic task to check for Final Submission Only contests that have ended
    and trigger judging for their pending submissions.
    Only processes contests with auto_judge enabled.
    Runs every minute to ensure immediate judging after contest ends.
    """
    import logging
    from django.db.models import F
    from django.utils import timezone

    logger = logging.getLogger('judge.tasks.contest')

    # Only contests that have ended and have not already been claimed for their current end_time.
    # Excluding claimed contests in SQL keeps this cheap as FSO contests accumulate -- previously
    # every FSO contest that had ever ended was re-examined on every single run.
    now = timezone.now()
    ended_contests = Contest.objects.filter(
        format_name='final_submission',
        end_time__lte=now,
    ).exclude(fso_judged_end_time=F('end_time'))

    processed_count = 0
    for contest in ended_contests:
        if not contest.is_fso_auto_judge_pending():
            continue

        # Atomic claim: exactly one caller wins per (contest, end_time), across processes and
        # restarts. Losing the race simply means someone else is already handling this contest.
        if not contest.claim_fso_auto_judge():
            logger.info('Skipping %s: already claimed by another process', contest.key)
            continue

        logger.info('✓ Triggering judge task for contest %s', contest.key)
        judge_final_submissions.delay(contest.key, rejudge_all=False)
        processed_count += 1

    if processed_count:
        logger.info('=== Periodic check completed: processed %s contests ===', processed_count)
    return processed_count
