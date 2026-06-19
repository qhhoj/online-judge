import uuid
from unittest.mock import patch

from cryptography.fernet import Fernet
from django.test import TestCase, override_settings

from judge.external_judge import finalize_external_submission, perform_external_submission, schedule_external_submission
from judge.judgeapi import judge_submission
from judge.models import (
    ExternalJudgeConfig,
    ExternalProblem,
    ExternalSubmission,
    Language,
    Submission,
    SubmissionSource,
)
from judge.models.tests.util import CommonDataMixin, create_problem
from judge.tasks.external_judge import submit_external_submission


TEST_FERNET_KEY = Fernet.generate_key().decode()


@override_settings(EXTERNAL_JUDGE_ENCRYPTION_KEY=TEST_FERNET_KEY)
class ExternalJudgeAsyncTests(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.external_config = ExternalJudgeConfig.objects.create(
            name='test-vjudge',
            base_url='https://example-vjudge.invalid',
            is_active=True,
            token_prefix='test',
            encrypted_api_token=' ',
        )
        cls.external_config.set_api_token('dummy-token')
        cls.external_config.save()

        cls.external_problem = create_problem(code='ext-problem')
        ExternalProblem.objects.create(
            problem=cls.external_problem,
            config=cls.external_config,
            oj='ext-oj',
            external_problem_id='1000',
            language_mappings=[
                {
                    'qhhoj_key': Language.get_python3().key,
                    'vjudge_id': '9001',
                },
            ],
        )

        cls.external_submission = Submission.objects.create(
            user=cls.users['normal'].profile,
            problem=cls.external_problem,
            language=Language.get_python3(),
            status='QU',
            case_total=100,
        )
        SubmissionSource.objects.create(
            submission=cls.external_submission,
            source='print(1)',
        )

        cls.normal_problem = create_problem(code='normal-problem')
        cls.normal_submission = Submission.objects.create(
            user=cls.users['normal'].profile,
            problem=cls.normal_problem,
            language=Language.get_python3(),
            status='QU',
            case_total=100,
        )
        SubmissionSource.objects.create(
            submission=cls.normal_submission,
            source='print(1)',
        )

    def test_external_judge_submission_schedules_task(self):
        with patch('judge.tasks.external_judge.submit_external_submission.apply_async') as apply_async_mock:
            with patch('judge.external_judge.ExternalJudgeClient.submit') as submit_mock:
                result = judge_submission(self.external_submission)

        self.assertTrue(result)
        self.assertTrue(ExternalSubmission.objects.filter(submission=self.external_submission).exists())
        apply_async_mock.assert_called_once()
        submit_mock.assert_not_called()
        task_args = apply_async_mock.call_args.kwargs['args']
        ext_sub = ExternalSubmission.objects.get(submission=self.external_submission)
        self.assertEqual(task_args[0], self.external_submission.id)
        self.assertEqual(task_args[1], False)
        self.assertEqual(task_args[2], False)
        self.assertEqual(task_args[3], str(ext_sub.pcd_submission_id))

    def test_submit_external_submission_task_submits_and_polls(self):
        placeholder = uuid.uuid4()
        ExternalSubmission.objects.create(
            submission=self.external_submission,
            config=self.external_config,
            pcd_submission_id=placeholder,
            pcd_system_status='queued',
        )
        remote_submission_id = uuid.uuid4()

        with patch('judge.tasks.external_judge.poll_external_submission.apply_async') as poll_apply_async:
            with patch('judge.external_judge.ExternalJudgeClient.submit') as submit_mock:
                submit_mock.return_value = {
                    'submissionId': str(remote_submission_id),
                    'systemStatus': 'queued',
                }
                result = perform_external_submission(
                    self.external_submission,
                    expected_pcd_submission_id=str(placeholder),
                )

        self.assertTrue(result)
        submit_mock.assert_called_once_with(
            oj=self.external_problem.external_problem.oj,
            problem_id=self.external_problem.external_problem.external_problem_id,
            language='9001',
            source='print(1)',
            open=True,
        )
        poll_apply_async.assert_called_once()
        poll_kwargs = poll_apply_async.call_args.kwargs
        self.assertEqual(poll_kwargs['args'], [self.external_submission.id, str(remote_submission_id)])
        self.assertEqual(poll_kwargs['countdown'], self.external_config.poll_interval_seconds)

        self.external_submission.refresh_from_db()
        self.assertEqual(str(self.external_submission.external_submission.pcd_submission_id), str(remote_submission_id))
        self.assertNotEqual(str(self.external_submission.external_submission.pcd_submission_id), str(placeholder))

    def test_selected_external_language_is_used_by_async_worker(self):
        selected_mapping = {
            'qhhoj_key': Language.get_python3().key,
            'vjudge_id': 'selected-remote-language',
            'vjudge_name': 'Selected remote language',
        }
        self.external_submission._external_language_mapping = selected_mapping

        with patch('judge.tasks.external_judge.submit_external_submission.apply_async'):
            result = schedule_external_submission(self.external_submission)

        self.assertTrue(result)
        ext_sub = ExternalSubmission.objects.get(submission=self.external_submission)
        self.assertEqual(
            ext_sub.raw_response['_qhhoj_selected_external_language']['vjudge_id'],
            selected_mapping['vjudge_id'],
        )
        remote_submission_id = uuid.uuid4()

        with patch('judge.tasks.external_judge.poll_external_submission.apply_async'):
            with patch('judge.external_judge.ExternalJudgeClient.submit') as submit_mock:
                submit_mock.return_value = {
                    'submissionId': str(remote_submission_id),
                    'systemStatus': 'queued',
                }
                result = perform_external_submission(
                    self.external_submission,
                    expected_pcd_submission_id=str(ext_sub.pcd_submission_id),
                )

        self.assertTrue(result)
        submit_mock.assert_called_once()
        self.assertEqual(submit_mock.call_args.kwargs['language'], selected_mapping['vjudge_id'])

    def test_rejudge_reuses_previous_selected_external_language(self):
        selected_mapping = {
            'qhhoj_key': 'remote-only-key',
            'vjudge_id': 'previously-selected-remote-language',
            'vjudge_name': 'Previously selected remote language',
        }
        old_pcd_submission_id = uuid.uuid4()
        ExternalSubmission.objects.create(
            submission=self.external_submission,
            config=self.external_config,
            pcd_submission_id=old_pcd_submission_id,
            pcd_system_status='done',
            raw_response={
                '_qhhoj_selected_external_language': selected_mapping,
            },
        )

        with patch('judge.tasks.external_judge.submit_external_submission.apply_async'):
            result = schedule_external_submission(self.external_submission, rejudge=True)

        self.assertTrue(result)
        ext_sub = ExternalSubmission.objects.get(submission=self.external_submission)
        self.assertNotEqual(str(ext_sub.pcd_submission_id), str(old_pcd_submission_id))
        self.assertEqual(
            ext_sub.raw_response['_qhhoj_selected_external_language']['vjudge_id'],
            selected_mapping['vjudge_id'],
        )

        remote_submission_id = uuid.uuid4()
        with patch('judge.tasks.external_judge.poll_external_submission.apply_async'):
            with patch('judge.external_judge.ExternalJudgeClient.submit') as submit_mock:
                submit_mock.return_value = {
                    'submissionId': str(remote_submission_id),
                    'systemStatus': 'queued',
                }
                result = perform_external_submission(
                    self.external_submission,
                    expected_pcd_submission_id=str(ext_sub.pcd_submission_id),
                )

        self.assertTrue(result)
        submit_mock.assert_called_once()
        self.assertEqual(submit_mock.call_args.kwargs['language'], selected_mapping['vjudge_id'])

    def test_external_problem_language_mapping_is_case_insensitive(self):
        external_problem = self.external_problem.external_problem
        external_problem.language_mappings = [{
            'qhhoj_key': Language.get_python3().key.lower(),
            'vjudge_id': 'case-insensitive-language',
            'vjudge_name': 'Case insensitive language',
        }]
        self.assertEqual(
            external_problem.get_language_mapping(Language.get_python3())['vjudge_id'],
            'case-insensitive-language',
        )

    def test_submit_external_submission_updates_without_expected_placeholder(self):
        stale_placeholder = uuid.uuid4()
        ExternalSubmission.objects.create(
            submission=self.external_submission,
            config=self.external_config,
            pcd_submission_id=stale_placeholder,
            pcd_system_status='queued',
        )
        remote_submission_id = uuid.uuid4()

        with patch('judge.tasks.external_judge.poll_external_submission.apply_async') as poll_apply_async:
            with patch('judge.external_judge.ExternalJudgeClient.submit') as submit_mock:
                submit_mock.return_value = {
                    'submissionId': str(remote_submission_id),
                    'systemStatus': 'queued',
                }
                result = perform_external_submission(self.external_submission)

        self.assertTrue(result)
        poll_apply_async.assert_called_once()
        self.external_submission.refresh_from_db()
        self.assertEqual(str(self.external_submission.external_submission.pcd_submission_id), str(remote_submission_id))

    def test_submit_failed_status_is_case_insensitive_and_keeps_raw_response(self):
        placeholder = uuid.uuid4()
        ExternalSubmission.objects.create(
            submission=self.external_submission,
            config=self.external_config,
            pcd_submission_id=placeholder,
            pcd_system_status='queued',
        )

        with patch('judge.external_judge.ExternalJudgeClient.submit') as submit_mock:
            submit_mock.return_value = {
                'submissionId': None,
                'systemStatus': 'SUBMIT_FAILED_LANGUAGE',
                'errorMessage': 'Remote rejected language',
            }
            result = perform_external_submission(
                self.external_submission,
                expected_pcd_submission_id=str(placeholder),
            )

        self.assertFalse(result)
        self.external_submission.refresh_from_db()
        ext_sub = self.external_submission.external_submission
        self.assertEqual(self.external_submission.status, 'IE')
        self.assertEqual(self.external_submission.result, 'IE')
        self.assertEqual(self.external_submission.error, 'Remote rejected language')
        self.assertEqual(ext_sub.pcd_system_status, 'SUBMIT_FAILED_LANGUAGE')
        self.assertEqual(ext_sub.raw_response['systemStatus'], 'SUBMIT_FAILED_LANGUAGE')

    def test_finalize_timeout_maps_to_tle(self):
        ext_sub = ExternalSubmission.objects.create(
            submission=self.external_submission,
            config=self.external_config,
            pcd_submission_id=uuid.uuid4(),
            pcd_system_status='done',
        )
        self.external_submission.status = 'P'
        self.external_submission.save(update_fields=['status'])

        with patch('judge.external_judge._finish_submission_updates') as finish_mock:
            result = finalize_external_submission(self.external_submission, ext_sub, {
                'systemStatus': 'done',
                'statusCanonical': 'TIMEOUT',
                'runtimeMs': 1234,
                'memoryKb': 2048,
            })

        self.assertTrue(result)
        finish_mock.assert_called_once()
        self.external_submission.refresh_from_db()
        self.assertEqual(self.external_submission.status, 'D')
        self.assertEqual(self.external_submission.result, 'TLE')
        self.assertEqual(self.external_submission.time, 1.234)
        self.assertEqual(self.external_submission.memory, 2048)

    def test_finalize_pending_status_does_not_mark_internal_error(self):
        ext_sub = ExternalSubmission.objects.create(
            submission=self.external_submission,
            config=self.external_config,
            pcd_submission_id=uuid.uuid4(),
            pcd_system_status='queued',
        )
        self.external_submission.status = 'P'
        self.external_submission.save(update_fields=['status'])

        with patch('judge.external_judge._finish_submission_updates') as finish_mock:
            result = finalize_external_submission(self.external_submission, ext_sub, {
                'systemStatus': 'done',
                'statusCanonical': 'PENDING',
                'processing': False,
            })

        self.assertFalse(result)
        finish_mock.assert_not_called()
        self.external_submission.refresh_from_db()
        self.assertEqual(self.external_submission.status, 'P')
        self.assertIsNone(self.external_submission.result)

    def test_finalize_unknown_status_uses_error_message(self):
        ext_sub = ExternalSubmission.objects.create(
            submission=self.external_submission,
            config=self.external_config,
            pcd_submission_id=uuid.uuid4(),
            pcd_system_status='done',
        )
        self.external_submission.status = 'P'
        self.external_submission.save(update_fields=['status'])

        with patch('judge.external_judge._finish_submission_updates') as finish_mock:
            result = finalize_external_submission(self.external_submission, ext_sub, {
                'systemStatus': 'done',
                'statusCanonical': 'REMOTE_BROKEN',
                'errorMessage': 'Remote returned a broken verdict',
            })

        self.assertTrue(result)
        finish_mock.assert_called_once()
        self.external_submission.refresh_from_db()
        self.assertEqual(self.external_submission.status, 'IE')
        self.assertEqual(self.external_submission.result, 'IE')
        self.assertEqual(self.external_submission.error, 'Remote returned a broken verdict')

    def test_stale_submit_result_does_not_overwrite_new_placeholder(self):
        old_placeholder = uuid.uuid4()
        new_placeholder = uuid.uuid4()
        ExternalSubmission.objects.create(
            submission=self.external_submission,
            config=self.external_config,
            pcd_submission_id=old_placeholder,
            pcd_system_status='queued',
        )
        remote_submission_id = uuid.uuid4()

        def submit_side_effect(**_kwargs):
            ExternalSubmission.objects.filter(submission=self.external_submission).update(
                pcd_submission_id=new_placeholder,
            )
            return {
                'submissionId': str(remote_submission_id),
                'systemStatus': 'queued',
            }

        with patch('judge.tasks.external_judge.poll_external_submission.apply_async') as poll_apply_async:
            with patch('judge.external_judge.ExternalJudgeClient.submit', side_effect=submit_side_effect):
                result = perform_external_submission(
                    self.external_submission,
                    expected_pcd_submission_id=str(old_placeholder),
                )

        self.assertFalse(result)
        poll_apply_async.assert_not_called()
        self.external_submission.refresh_from_db()
        self.assertEqual(str(self.external_submission.external_submission.pcd_submission_id), str(new_placeholder))

    def test_submit_external_submission_task_delegates_to_background_helper(self):
        expected_task_id = str(uuid.uuid4())
        with patch('judge.tasks.external_judge.perform_external_submission') as perform_external_mock:
            submit_external_submission.run(
                self.external_submission.id,
                rejudge=True,
                batch_rejudge=False,
                expected_pcd_submission_id=expected_task_id,
            )

        self.assertEqual(perform_external_mock.call_count, 1)
        call_kwargs = perform_external_mock.call_args[1]
        self.assertEqual(call_kwargs['rejudge'], True)
        self.assertEqual(call_kwargs['batch_rejudge'], False)
        self.assertEqual(call_kwargs['expected_pcd_submission_id'], expected_task_id)
        self.assertEqual(perform_external_mock.call_args[0][0].id, self.external_submission.id)

    def test_schedule_external_submission_enqueue_failure_marks_submission_error(self):
        with patch(
            'judge.tasks.external_judge.submit_external_submission.apply_async',
            side_effect=RuntimeError('queue down'),
        ):
            result = schedule_external_submission(self.external_submission)

        self.assertFalse(result)
        self.external_submission.refresh_from_db()
        self.assertEqual(self.external_submission.status, 'IE')
        self.assertEqual(self.external_submission.result, 'IE')

    def test_normal_submission_uses_bridge_not_external_task(self):
        with patch('judge.external_judge.schedule_external_submission') as schedule_mock:
            with patch('judge.judgeapi.judge_request') as judge_request_mock:
                judge_request_mock.return_value = {
                    'name': 'submission-received',
                    'submission-id': self.normal_submission.id,
                }
                result = judge_submission(self.normal_submission)

        self.assertTrue(result)
        schedule_mock.assert_not_called()
        judge_request_mock.assert_called_once()
