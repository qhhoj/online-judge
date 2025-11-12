"""
FSO Contest Scheduler - Automatically triggers judging when contest ends.
Uses threading.Timer to schedule judging without requiring Celery or cron.
"""
import logging
import threading
from datetime import datetime

from django.utils import timezone
from django.core.cache import cache

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
    from judge.models import Contest
    
    # Only for FSO contests
    if contest.format_name != 'final_submission':
        return
    
    # Check if auto_judge is enabled
    format_config = contest.format_config or {}
    auto_judge = format_config.get('auto_judge', True)
    if not auto_judge:
        logger.info(f'FSO contest {contest.key}: auto_judge disabled, skipping scheduler')
        return
    
    # Calculate delay until contest ends
    now = timezone.now()
    end_time = contest.end_time
    
    if end_time <= now:
        # Contest already ended, trigger immediately
        logger.info(f'FSO contest {contest.key} already ended, triggering immediately')
        _trigger_judging(contest.key)
        return
    
    # Calculate delay in seconds
    delay = (end_time - now).total_seconds()
    
    # Cancel existing timer for this contest (if any)
    with _timer_lock:
        if contest.id in _scheduled_timers:
            old_timer = _scheduled_timers[contest.id]
            old_timer.cancel()
            logger.info(f'Cancelled old timer for contest {contest.key}')
    
    # Schedule new timer
    timer = threading.Timer(delay, _trigger_judging, args=[contest.key])
    timer.daemon = True  # Daemon thread will exit when main program exits
    timer.start()
    
    with _timer_lock:
        _scheduled_timers[contest.id] = timer
    
    logger.info(
        f'Scheduled FSO contest {contest.key} for judging at {end_time} '
        f'(in {delay:.0f} seconds / {delay/60:.1f} minutes)'
    )


def _trigger_judging(contest_key):
    """
    Trigger judging for an FSO contest.
    Called by timer when contest ends.
    """
    from judge.models import Contest, Submission
    from judge.tasks.contest import _judge_final_submissions_impl
    
    logger.info(f'=== Timer triggered for contest {contest_key} ===')
    
    try:
        contest = Contest.objects.get(key=contest_key)
    except Contest.DoesNotExist:
        logger.error(f'Contest {contest_key} not found')
        return
    
    # Use cache to ensure we only trigger once per end_time
    end_time_ts = int(contest.end_time.timestamp())
    cache_key = f'fso_judged_{contest.id}_{end_time_ts}'
    
    if cache.get(cache_key):
        logger.info(f'Contest {contest_key} already judged for this end_time (cache hit)')
        return
    
    # Check if there are any submissions
    total_count = Submission.objects.filter(
        contest__participation__contest=contest,
    ).count()
    
    if total_count == 0:
        logger.info(f'Contest {contest_key} has no submissions, skipping')
        return
    
    # Mark as triggered
    cache.set(cache_key, True, 86400)  # Cache for 24 hours
    
    logger.info(f'Triggering judging for contest {contest_key} ({total_count} submissions)')
    
    # Call judging implementation directly (synchronous)
    try:
        result = _judge_final_submissions_impl(contest_key, rejudge_all=False)
        logger.info(f'Judging completed: {result.get("message", "success")}')
    except Exception as e:
        logger.error(f'Error judging contest {contest_key}: {e}', exc_info=True)
    
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
            logger.info(f'Cancelled timer for contest ID {contest_id}')
        _scheduled_timers.clear()


def reschedule_all_fso_contests():
    """
    Reschedule all pending FSO contests.
    Called when server starts to restore timers.
    """
    from judge.models import Contest
    from django.utils import timezone
    
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
    
    logger.info(f'Rescheduled {count} FSO contests')
    return count

