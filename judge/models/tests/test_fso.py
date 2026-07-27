from unittest import mock

from django.test import TestCase
from django.utils import timezone

from judge.models import (
    Contest,
    ContestSubmission,
    Language,
    Submission,
    SubmissionSource,
    SubmissionTestCase,
)
from judge.models.tests.util import (
    CommonDataMixin,
    create_contest,
    create_contest_participation,
    create_contest_problem,
    create_problem,
)


def _end_contest_now(contest):
    """
    Move a contest's end time into the past without going through save().

    Saving an FSO contest fires judge/signals.py:contest_update, which calls
    schedule_fso_contest_judging; for a contest that has already ended that runs the judging path
    synchronously, claiming the contest before the test gets to it. A queryset update skips the
    post_save signal, so tests control when judging is triggered.
    """
    ended_at = timezone.now() - timezone.timedelta(days=1)
    Contest.objects.filter(pk=contest.pk).update(end_time=ended_at)
    contest.refresh_from_db()
    return contest


def _ended_fso_contest(key, **kwargs):
    now = timezone.now()
    kwargs.setdefault('format_name', 'final_submission')
    contest = create_contest(
        key,
        start_time=now - timezone.timedelta(days=2),
        end_time=now + timezone.timedelta(days=1),
        **kwargs,
    )
    return _end_contest_now(contest)


class FSOAutoJudgeClaimTestCase(CommonDataMixin, TestCase):
    """
    The claim is what stops a Final Submission Only contest from being auto-judged more than once.

    It used to be a LocMemCache entry with a 24 hour TTL, which meant every ended FSO contest was
    re-judged once a day, once per worker process, and again after every restart -- each run
    deleting and regenerating every submission's test case results. These tests pin down the
    replacement: a database-backed claim that is granted exactly once per (contest, end_time).
    """

    def test_claim_granted_once(self):
        contest = _ended_fso_contest('fso_once')

        self.assertTrue(contest.claim_fso_auto_judge())
        self.assertFalse(contest.claim_fso_auto_judge())
        self.assertFalse(contest.claim_fso_auto_judge())

    def test_claim_is_not_process_local(self):
        # A second process sees the same contest row, not its own empty cache. Two model instances
        # loaded independently stand in for two workers.
        _ended_fso_contest('fso_two_workers')

        worker_one = Contest.objects.get(key='fso_two_workers')
        worker_two = Contest.objects.get(key='fso_two_workers')

        self.assertTrue(worker_one.claim_fso_auto_judge())
        self.assertFalse(worker_two.claim_fso_auto_judge())

    def test_claim_survives_reload(self):
        # Standing in for a process restart: the marker is durable, so a fresh instance cannot
        # re-claim. This is the case the old cache guard could never handle.
        contest = _ended_fso_contest('fso_restart')
        self.assertTrue(contest.claim_fso_auto_judge())

        self.assertFalse(Contest.objects.get(key='fso_restart').claim_fso_auto_judge())

    def test_claim_persists_marker(self):
        contest = _ended_fso_contest('fso_marker')
        contest.claim_fso_auto_judge()

        self.assertEqual(Contest.objects.get(key='fso_marker').fso_judged_end_time, contest.end_time)

    def test_extending_contest_rearms_claim(self):
        # Extending the end time is a deliberate re-arm: the contest genuinely needs judging again
        # at its new end time.
        contest = _ended_fso_contest('fso_extended')
        self.assertTrue(contest.claim_fso_auto_judge())

        Contest.objects.filter(pk=contest.pk).update(
            end_time=timezone.now() - timezone.timedelta(minutes=1),
        )
        contest.refresh_from_db()

        self.assertTrue(contest.claim_fso_auto_judge())

    def test_pending_reflects_claim(self):
        contest = _ended_fso_contest('fso_pending')
        self.assertTrue(contest.is_fso_auto_judge_pending())

        contest.claim_fso_auto_judge()
        self.assertFalse(contest.is_fso_auto_judge_pending())

    def test_not_pending_for_other_formats(self):
        contest = _ended_fso_contest('fso_other_format', format_name='default')
        self.assertFalse(contest.is_fso_auto_judge_pending())

    def test_not_pending_before_contest_ends(self):
        now = timezone.now()
        contest = create_contest(
            'fso_running',
            format_name='final_submission',
            start_time=now - timezone.timedelta(hours=1),
            end_time=now + timezone.timedelta(hours=1),
        )
        self.assertFalse(contest.is_fso_auto_judge_pending())

    def test_not_pending_when_auto_judge_disabled(self):
        contest = _ended_fso_contest('fso_manual', format_config={'auto_judge': False})
        self.assertFalse(contest.is_fso_auto_judge_pending())


class FSOTriggerTestCase(CommonDataMixin, TestCase):
    """The callers that hang off the claim: page views and the periodic check."""

    def test_page_view_trigger_fires_once(self):
        # trigger_final_submission_judging runs on every render of an ended FSO contest, from
        # ContestDetail and the ranking view. It must dispatch at most once no matter how many
        # times the page is loaded.
        contest = _ended_fso_contest('fso_pageview')

        with mock.patch('judge.tasks.contest.judge_final_submissions.delay') as delay:
            self.assertTrue(contest.trigger_final_submission_judging())
            self.assertFalse(contest.trigger_final_submission_judging())
            self.assertFalse(contest.trigger_final_submission_judging())

        delay.assert_called_once_with('fso_pageview', rejudge_all=False)

    def test_page_view_trigger_ignores_disabled_auto_judge(self):
        contest = _ended_fso_contest('fso_pageview_off', format_config={'auto_judge': False})

        with mock.patch('judge.tasks.contest.judge_final_submissions.delay') as delay:
            self.assertFalse(contest.trigger_final_submission_judging())

        delay.assert_not_called()

    def test_periodic_check_does_not_requeue_claimed_contests(self):
        from judge.tasks.contest import check_final_submission_contests

        _ended_fso_contest('fso_periodic')

        with mock.patch('judge.tasks.contest.judge_final_submissions.delay') as delay:
            self.assertEqual(check_final_submission_contests(), 1)
            # The second and third runs stand in for the next beat ticks. Under the old cache guard
            # these re-fired once the 24 hour TTL lapsed.
            self.assertEqual(check_final_submission_contests(), 0)
            self.assertEqual(check_final_submission_contests(), 0)

        self.assertEqual(delay.call_count, 1)

    def test_periodic_check_skips_disabled_auto_judge(self):
        from judge.tasks.contest import check_final_submission_contests

        _ended_fso_contest('fso_periodic_off', format_config={'auto_judge': False})

        with mock.patch('judge.tasks.contest.judge_final_submissions.delay') as delay:
            self.assertEqual(check_final_submission_contests(), 0)

        delay.assert_not_called()

    def test_periodic_check_dispatches_non_destructively(self):
        from judge.tasks.contest import check_final_submission_contests

        _ended_fso_contest('fso_periodic_flag')

        with mock.patch('judge.tasks.contest.judge_final_submissions.delay') as delay:
            check_final_submission_contests()

        # Automatic triggers must never reset already-judged submissions.
        delay.assert_called_once_with('fso_periodic_flag', rejudge_all=False)


class FSOJudgeSelectionTestCase(CommonDataMixin, TestCase):
    """
    Which submissions each mode of _judge_final_submissions_impl touches.

    The automatic path must leave finished submissions alone -- that is what made repeated triggers
    destructive, since every run deleted and regenerated the whole contest's test case results.
    """

    @classmethod
    def setUpTestData(self):
        super().setUpTestData()
        self.contest = _ended_fso_contest('fso_selection')
        self.problem = create_problem(code='fso_selection_problem')
        self.contest_problem = create_contest_problem(contest=self.contest, problem=self.problem)
        self.participation = create_contest_participation(
            contest=self.contest, user=self.users['normal'].profile,
        )

    def _submit(self, status, result=None):
        submission = Submission.objects.create(
            user=self.users['normal'].profile,
            problem=self.problem,
            language=Language.get_python3(),
            status=status,
            result=result,
            points=10 if status == 'D' else None,
        )
        SubmissionSource.objects.create(submission=submission, source='')
        ContestSubmission.objects.create(
            submission=submission,
            problem=self.contest_problem,
            participation=self.participation,
        )
        SubmissionTestCase.objects.create(
            submission=submission, case=1, status=result or 'AC', points=1, total=1,
        )
        return submission

    def _run(self, rejudge_all):
        from judge.tasks.contest import _judge_final_submissions_impl

        # judge_submission talks to the bridge over TCP; the selection logic is what is under test.
        with mock.patch('judge.judgeapi.judge_submission', return_value=True):
            return _judge_final_submissions_impl(self.contest.key, rejudge_all=rejudge_all)

    def test_automatic_run_leaves_finished_submissions_alone(self):
        done = self._submit('D', 'AC')
        pending = self._submit('PD')

        result = self._run(rejudge_all=False)

        self.assertEqual(result['queued_count'], 1)
        done.refresh_from_db()
        pending.refresh_from_db()
        self.assertEqual(done.status, 'D')
        self.assertEqual(done.result, 'AC')
        self.assertEqual(pending.status, 'QU')
        # The finished submission keeps its test case results.
        self.assertEqual(SubmissionTestCase.objects.filter(submission=done).count(), 1)

    def test_automatic_run_is_idempotent(self):
        done = self._submit('D', 'AC')
        self._submit('PD')

        self._run(rejudge_all=False)
        second = self._run(rejudge_all=False)

        # Everything is either queued or finished by now, so a repeat run has nothing to do.
        self.assertEqual(second['queued_count'], 0)
        done.refresh_from_db()
        self.assertEqual(done.status, 'D')
        self.assertEqual(SubmissionTestCase.objects.filter(submission=done).count(), 1)

    def test_automatic_run_picks_up_stalled_submissions(self):
        internal_error = self._submit('IE')

        self.assertEqual(self._run(rejudge_all=False)['queued_count'], 1)
        internal_error.refresh_from_db()
        self.assertEqual(internal_error.status, 'QU')

    def test_explicit_rejudge_resets_everything(self):
        done = self._submit('D', 'AC')
        pending = self._submit('PD')

        result = self._run(rejudge_all=True)

        self.assertEqual(result['queued_count'], 2)
        done.refresh_from_db()
        pending.refresh_from_db()
        self.assertEqual(done.status, 'QU')
        self.assertIsNone(done.result)
        self.assertEqual(pending.status, 'QU')
        self.assertEqual(SubmissionTestCase.objects.count(), 0)

    def test_neither_mode_touches_submissions_being_graded(self):
        grading = self._submit('G')

        self._run(rejudge_all=True)

        grading.refresh_from_db()
        self.assertEqual(grading.status, 'G')
