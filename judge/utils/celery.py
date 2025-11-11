from celery.result import AsyncResult
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.http import urlencode


class Progress:
    def __init__(self, task, total, stage=None):
        self.task = task
        self._total = total
        self._done = 0
        self._stage = stage

    def _update_state(self):
        self.task.update_state(
            state='PROGRESS',
            meta={
                'done': self._done,
                'total': self._total,
                'stage': self._stage,
            },
        )

    @property
    def done(self):
        return self._done

    @done.setter
    def done(self, value):
        self._done = value
        self._update_state()

    @property
    def total(self):
        return self._total

    @total.setter
    def total(self, value):
        self._total = value
        self._done = min(self._done, value)
        self._update_state()

    def did(self, delta):
        self._done += delta
        self._update_state()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.done = self._total


def task_status_url_by_id(result_id, message=None, redirect=None):
    args = {}
    if message:
        args['message'] = message
    if redirect:
        args['redirect'] = redirect
    url = reverse('task_status', args=[result_id])
    if args:
        url += '?' + urlencode(args)
    return url


def task_status_url(result, message=None, redirect=None):
    # Handle both AsyncResult and string task IDs
    from celery.result import AsyncResult

    if isinstance(result, AsyncResult):
        task_id = result.id
    elif isinstance(result, str):
        task_id = result
    elif hasattr(result, 'id'):
        task_id = result.id
    else:
        # If result is not AsyncResult (e.g., when CELERY_ALWAYS_EAGER=True),
        # we can't track progress, so create a fake task ID
        import logging
        import uuid
        logger = logging.getLogger('judge.utils.celery')
        logger.warning(f'Task result is not AsyncResult: {type(result)} - {result}')
        task_id = str(uuid.uuid4())
    return task_status_url_by_id(task_id, message, redirect)


def redirect_to_task_status(result, message=None, redirect=None):
    # If result is not AsyncResult and redirect is available, go there directly
    from celery.result import AsyncResult
    if not isinstance(result, AsyncResult) and not isinstance(result, str) and not hasattr(result, 'id'):
        if redirect:
            import logging
            logger = logging.getLogger('judge.utils.celery')
            logger.info(f'Task completed synchronously, redirecting to: {redirect}')
            return HttpResponseRedirect(redirect)

    return HttpResponseRedirect(task_status_url(result, message, redirect))


def task_status_by_id(result_id):
    return AsyncResult(result_id)
