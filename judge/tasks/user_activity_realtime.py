import logging

from celery import shared_task

from judge.utils.user_activity_realtime import refresh_realtime_snapshot


logger = logging.getLogger(__name__)


@shared_task
def refresh_user_activity_realtime_snapshot():
    """
    Periodically build realtime snapshot from Redis state.
    Keeps request path fast for admin tracking dashboard.
    """
    ok = refresh_realtime_snapshot()
    if not ok:
        logger.debug('Realtime user activity snapshot skipped or unavailable')
    return ok
