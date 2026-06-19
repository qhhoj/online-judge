"""
FSO Contest Scheduler - Automatically triggers judging when contest ends.
Uses threading.Timer to schedule judging without requiring Celery or cron.
"""
import logging
import threading

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger('judge.fso_scheduler')

# Global dict to track scheduled timers: {contest_id: timer_object}
_scheduled_timers = {}
_timer_lock = threading.Lock()


def schedule_fso_contest_judging(contest):
    """
    Schedule automatic judging for an FSO contest when it ends.

    Args:
        contest: Contest instance
    """
    # Only for FSO contests
    if contest.format_name != 'final_submission':
        return

    # Check if auto_judge is enabled
    format_config = contest.format_config or {}
    auto_judge = format_config.get('auto_judge', True)
    if not auto_judge:
        logger.info('FSO contest %s: auto_judge disabled, skipping scheduler', contest.key)
        return

    # Calculate delay until contest ends
    now = timezone.now()
    end_time = contest.end_time

    if end_time <= now:
        # Contest already ended, trigger immediately
        logger.info('FSO contest %s already ended, triggering immediately', contest.key)
        _trigger_judging(contest.key)
        return

    # Calculate delay in seconds
    delay = (end_time - now).total_seconds()

    # Cancel existing timer for this contest (if any)
    with _timer_lock:
        if contest.id in _scheduled_timers:
            old_timer = _scheduled_timers[contest.id]
            old_timer.cancel()
            logger.info('Cancelled old timer for contest %s', contest.key)

    # Schedule new timer
    timer = threading.Timer(delay, _trigger_judging, args=[contest.key])
    timer.daemon = True  # Daemon thread will exit when main program exits
    timer.start()

    with _timer_lock:
        _scheduled_timers[contest.id] = timer

    logger.info(
        'Scheduled FSO contest %s for judging at %s (in %.0f seconds / %.1f minutes)',
        contest.key, end_time, delay, delay / 60,
    )


def _trigger_judging(contest_key):
    """
    Trigger judging for an FSO contest.
    Called by timer when contest ends.
    """
    from judge.models import Contest, Submission
    from judge.tasks.contest import _judge_final_submissions_impl

    logger.info('=== Timer triggered for contest %s ===', contest_key)

    try:
        contest = Contest.objects.get(key=contest_key)
    except Contest.DoesNotExist:
        logger.error('Contest %s not found', contest_key)
        return

    # Use cache to ensure we only trigger once per end_time
    end_time_ts = int(contest.end_time.timestamp())
    cache_key = f'fso_judged_{contest.id}_{end_time_ts}'

    if cache.get(cache_key):
        logger.info('Contest %s already judged for this end_time (cache hit)', contest_key)
        return

    # Check if there are any submissions
    total_count = Submission.objects.filter(
        contest__participation__contest=contest,
    ).count()

    if total_count == 0:
        logger.info('Contest %s has no submissions, skipping', contest_key)
        return

    # Mark as triggered
    cache.set(cache_key, True, 86400)  # Cache for 24 hours

    logger.info('Triggering judging for contest %s (%s submissions)', contest_key, total_count)

    # Call judging implementation directly (synchronous)
    try:
        result = _judge_final_submissions_impl(contest_key, rejudge_all=False)
        logger.info('Judging completed: %s', result.get('message', 'success'))
    except Exception:
        logger.exception('Error judging contest %s', contest_key)

    # Remove timer from tracking dict
    with _timer_lock:
        if contest.id in _scheduled_timers:
            del _scheduled_timers[contest.id]


def cancel_all_timers():
    """
    Cancel all scheduled timers.
    Called when server shuts down.
    """
    with _timer_lock:
        for contest_id, timer in _scheduled_timers.items():
            timer.cancel()
            logger.info('Cancelled timer for contest ID %s', contest_id)
        _scheduled_timers.clear()


def reschedule_all_fso_contests():
    """
    Reschedule all pending FSO contests.
    Called when server starts to restore timers.
    """
    from django.utils import timezone

    from judge.models import Contest

    logger.info('=== Rescheduling all FSO contests ===')

    now = timezone.now()
    pending_contests = Contest.objects.filter(
        format_name='final_submission',
        end_time__gt=now,  # Not yet ended
    )

    count = 0
    for contest in pending_contests:
        schedule_fso_contest_judging(contest)
        count += 1

    logger.info('Rescheduled %s FSO contests', count)
    return count
