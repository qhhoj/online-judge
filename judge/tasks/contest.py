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


__all__ = ('rescore_contest', 'run_moss', 'prepare_contest_data', 'judge_final_submissions', 'check_final_submission_contests')
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


@shared_task(bind=True)
def judge_final_submissions(self, contest_key, rejudge_all=False):
    """
    Queue ALL submissions for a Final Submission Only contest for judging.
    Changes submission status from 'PD' (Pending) to 'QU' (Queued).
    Judge server will automatically pick up and process queued submissions.

    Args:
        contest_key: Contest key
        rejudge_all: If True, rejudge all submissions (not just pending ones)

    Reports progress that can be tracked via task state.
    """
    from django.utils import timezone
    from judge.models import SubmissionTestCase

    contest = Contest.objects.get(key=contest_key)

    # Verify this is a final_submission format contest
    if contest.format_name != 'final_submission':
        return {
            'status': 'error',
            'message': 'Not a Final Submission Only contest',
            'contest_key': contest_key,
        }

    # Get ALL submissions for this contest
    if rejudge_all:
        # Rejudge all submissions (not just pending)
        submissions = Submission.objects.filter(
            contest__participation__contest=contest,
        ).exclude(status__in=('P', 'G'))  # Exclude currently processing
    else:
        # Only queue pending submissions
        submissions = Submission.objects.filter(
            contest__participation__contest=contest,
            status='PD',  # Pending status
        )

    total_submissions = submissions.count()

    # Update initial state
    self.update_state(
        state='PROGRESS',
        meta={
            'current': 0,
            'total': total_submissions,
            'percent': 0,
            'contest_key': contest_key,
            'status': 'starting',
        },
    )

    if total_submissions == 0:
        return {
            'status': 'completed',
            'contest_key': contest_key,
            'queued_count': 0,
            'total': 0,
            'message': 'No submissions to queue',
        }

    stage_msg = _('Queueing submissions for judging')

    # For rejudge, delete old test cases
    if rejudge_all:
        submission_ids = list(submissions.values_list('id', flat=True))
        SubmissionTestCase.objects.filter(submission_id__in=submission_ids).delete()

    # Bulk update all submissions to Queued status
    # This is much faster than calling judge_submission() for each one
    update_fields = {
        'time': None,
        'memory': None,
        'points': None,
        'result': None,
        'case_points': 0,
        'case_total': 0,
        'error': None,
        'status': 'QU',  # Queued - judge server will pick up automatically
    }

    if rejudge_all:
        update_fields['rejudged_date'] = timezone.now()

    # Bulk update in one query - much faster!
    queued_count = submissions.update(**update_fields)

    # Now dispatch all submissions to judge server
    from judge.judgeapi import judge_submission

    # Get submission IDs before they're modified
    submission_ids = list(submissions.values_list('id', flat=True))

    # Dispatch all submissions to judge server
    # This will send them to bridge which will queue them
    dispatched = 0
    for submission_id in submission_ids:
        try:
            submission = Submission.objects.select_related('problem', 'language', 'source').get(id=submission_id)
            # Call judge_submission with rejudge=True to dispatch to bridge
            # This won't change status (already QU) but will send to bridge
            judge_submission(submission, rejudge=True, batch_rejudge=True)
            dispatched += 1
        except Exception:
            # If dispatch fails, submission will stay in QU and can be retried
            pass

    # Update progress to 100%
    self.update_state(
        state='PROGRESS',
        meta={
            'current': queued_count,
            'total': total_submissions,
            'percent': 100,
            'contest_key': contest_key,
            'queued_count': queued_count,
            'dispatched_count': dispatched,
            'status': 'completed',
        },
    )

    return {
        'status': 'completed',
        'contest_key': contest_key,
        'queued_count': queued_count,
        'dispatched_count': dispatched,
        'total': total_submissions,
        'message': f'Queued {queued_count} submissions and dispatched {dispatched} to judge server',
    }


@shared_task(bind=True)
def check_final_submission_contests(self):
    """
    Periodic task to check for Final Submission Only contests that have ended
    and trigger judging for their pending submissions.
    Only processes contests with auto_judge enabled.
    Runs every minute to ensure immediate judging after contest ends.
    """
    import logging
    from django.utils import timezone
    from django.core.cache import cache

    logger = logging.getLogger('judge.tasks.contest')

    # Find all final_submission contests that have ended
    now = timezone.now()
    ended_contests = Contest.objects.filter(
        format_name='final_submission',
        end_time__lte=now,
    )

    logger.info(f'Checking {ended_contests.count()} ended final_submission contests')

    processed_count = 0
    for contest in ended_contests:
        # Check if auto_judge is enabled (default: True)
        format_config = contest.format_config or {}
        auto_judge = format_config.get('auto_judge', True)

        if not auto_judge:
            continue

        # Use same cache key as trigger_final_submission_judging to avoid duplicate triggers
        end_time_ts = int(contest.end_time.timestamp())
        cache_key = f'fso_judged_{contest.id}_{end_time_ts}'

        # Skip if already triggered for this end_time
        if cache.get(cache_key):
            continue

        # Check if there are any pending submissions
        pending_count = Submission.objects.filter(
            contest__participation__contest=contest,
            status='PD',
        ).count()

        if pending_count > 0:
            # Mark as triggered (cache for 24 hours)
            cache.set(cache_key, True, 86400)

            # Trigger judging task for this contest
            logger.info(f'Triggering judge task for contest {contest.key} ({pending_count} pending submissions)')
            judge_final_submissions.delay(contest.key)
            processed_count += 1

    if processed_count > 0:
        logger.info(f'Processed {processed_count} contests')
    return processed_count
