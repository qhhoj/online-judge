import re
from datetime import datetime
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import resolve, reverse
from django.utils import timezone

from judge.models import ContestPublicRankingLink
from judge.models.tests.util import CommonDataMixin, create_contest, create_user


TOKEN_RE = re.compile(r'^[A-Za-z0-9]{18}$')


class PublicRankingLinkTestCase(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.manager = create_user(
            username='public_ranking_manager',
            is_staff=True,
            user_permissions=('edit_own_contest',),
        )
        cls.outsider = create_user(username='public_ranking_outsider')

    def make_contest(self, key, **kwargs):
        defaults = {
            'authors': (self.manager.username,),
            'is_private': True,
            'is_visible': True,
            'start_time': timezone.now() - timezone.timedelta(days=1),
            'end_time': timezone.now() + timezone.timedelta(days=1),
        }
        defaults.update(kwargs)
        return create_contest(key=key, **defaults)

    def assert_token_format(self, token):
        self.assertEqual(len(token), ContestPublicRankingLink.TOKEN_LENGTH)
        self.assertRegex(token, TOKEN_RE)

    def test_token_format_examples(self):
        # Feature: public-ranking-link, Property 1: Token sinh ra luôn đúng định dạng.
        for _ in range(100):
            self.assert_token_format(ContestPublicRankingLink.generate_token())

        contest = self.make_contest('public_link_token_format')
        link = ContestPublicRankingLink.create_for(contest)
        self.assert_token_format(link.token)
        link.regenerate()
        self.assert_token_format(link.token)

    def test_token_uniqueness_and_database_constraint(self):
        # Feature: public-ranking-link, Property 2: Token là duy nhất.
        links = [
            ContestPublicRankingLink.create_for(self.make_contest('public_link_unique_%02d' % i))
            for i in range(25)
        ]
        tokens = [link.token for link in links]
        self.assertEqual(len(tokens), len(set(tokens)))

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ContestPublicRankingLink.objects.create(
                    contest=self.make_contest('public_link_duplicate_token'),
                    token=tokens[0],
                    status=ContestPublicRankingLink.STATUS_PUBLIC,
                    expiry_mode=ContestPublicRankingLink.EXPIRY_UNLIMITED,
                    regenerated_at=timezone.now(),
                )

    def test_create_for_invariants(self):
        # Feature: public-ranking-link, Property 3: Bất biến khi tạo link.
        contest = self.make_contest('public_link_create_invariants')
        before = timezone.now()
        link = ContestPublicRankingLink.create_for(contest)
        after = timezone.now()

        self.assertEqual(link.contest, contest)
        self.assertEqual(link.status, ContestPublicRankingLink.STATUS_PUBLIC)
        self.assertEqual(link.expiry_mode, ContestPublicRankingLink.EXPIRY_UNLIMITED)
        self.assertIsNone(link.expiry_amount)
        self.assertIsNone(link.expires_at)
        self.assertGreaterEqual(link.regenerated_at, before)
        self.assertLessEqual(link.regenerated_at, after)

    def test_status_changes_preserve_token(self):
        # Feature: public-ranking-link, Property 4: Đổi trạng thái giữ nguyên token.
        link = ContestPublicRankingLink.create_for(self.make_contest('public_link_status'))
        token = link.token

        for status in (
            ContestPublicRankingLink.STATUS_PRIVATE,
            ContestPublicRankingLink.STATUS_PUBLIC,
            ContestPublicRankingLink.STATUS_PRIVATE,
        ):
            link.set_status(status)
            link.refresh_from_db()
            self.assertEqual(link.status, status)
            self.assertEqual(link.token, token)

    def test_regenerate_invalidates_old_token_at_model_level(self):
        # Feature: public-ranking-link, Property 8: Regenerate vô hiệu hoá token cũ.
        link = ContestPublicRankingLink.create_for(self.make_contest('public_link_regenerate_model'))
        old_token = link.token

        link.regenerate()
        link.refresh_from_db()

        self.assertNotEqual(link.token, old_token)
        self.assertFalse(ContestPublicRankingLink.objects.filter(token=old_token).exists())
        self.assert_token_format(link.token)

    def test_expiry_computation_and_validity(self):
        # Feature: public-ranking-link, Property 9: Tính thời điểm hết hạn.
        regenerated_at = timezone.now() - timezone.timedelta(hours=1)
        link = ContestPublicRankingLink.create_for(self.make_contest('public_link_expiry'))
        link.regenerated_at = regenerated_at
        link.save(update_fields=['regenerated_at'])

        self.assertIsNone(link.compute_expires_at())
        self.assertTrue(link.is_valid)

        link.configure_expiry(ContestPublicRankingLink.EXPIRY_MINUTES, 90)
        self.assertEqual(link.expires_at, regenerated_at + timezone.timedelta(minutes=90))
        self.assertTrue(link.is_valid)

        link.configure_expiry(ContestPublicRankingLink.EXPIRY_DAYS, 2)
        self.assertEqual(link.expires_at, regenerated_at + timezone.timedelta(days=2))
        self.assertTrue(link.is_valid)

        absolute_expires_at = (timezone.now() + timezone.timedelta(days=3)).replace(microsecond=0)
        link.configure_expiry(ContestPublicRankingLink.EXPIRY_DATETIME, expires_at=absolute_expires_at)
        self.assertEqual(link.expiry_mode, ContestPublicRankingLink.EXPIRY_DATETIME)
        self.assertIsNone(link.expiry_amount)
        self.assertEqual(link.expires_at, absolute_expires_at)
        self.assertTrue(link.is_valid)

        old_token = link.token
        link.regenerate()
        link.refresh_from_db()
        self.assertNotEqual(link.token, old_token)
        self.assertEqual(link.expiry_mode, ContestPublicRankingLink.EXPIRY_DATETIME)
        self.assertEqual(link.expires_at, absolute_expires_at)

        link.expires_at = timezone.now() - timezone.timedelta(seconds=1)
        link.save(update_fields=['expires_at'])
        self.assertFalse(link.is_valid)

        link.expires_at = None
        link.status = ContestPublicRankingLink.STATUS_PRIVATE
        link.save(update_fields=['expires_at', 'status'])
        self.assertFalse(link.is_valid)

    def test_invalid_expiry_amount_preserves_state(self):
        # Feature: public-ranking-link, Property 10: Từ chối khoảng thời gian không hợp lệ.
        link = ContestPublicRankingLink.create_for(self.make_contest('public_link_invalid_expiry'))
        link.configure_expiry(ContestPublicRankingLink.EXPIRY_DAYS, 3)
        original = (link.expiry_mode, link.expiry_amount, link.expires_at)

        for amount in (0, -1, None, '', 'abc', '1.5', 1.5, True):
            with self.subTest(amount=amount):
                with self.assertRaises(ValidationError):
                    link.configure_expiry(ContestPublicRankingLink.EXPIRY_MINUTES, amount)
                link.refresh_from_db()
                self.assertEqual((link.expiry_mode, link.expiry_amount, link.expires_at), original)

        for expires_at in (None, '', '2026-01-01 00:00:00', 123):
            with self.subTest(expires_at=expires_at):
                with self.assertRaises(ValidationError):
                    link.configure_expiry(ContestPublicRankingLink.EXPIRY_DATETIME, expires_at=expires_at)
                link.refresh_from_db()
                self.assertEqual((link.expiry_mode, link.expiry_amount, link.expires_at), original)

    def test_get_absolute_url_and_route_round_trip(self):
        # Feature: public-ranking-link, Property 5: Đường dẫn round-trip với token.
        link = ContestPublicRankingLink.create_for(self.make_contest('public_link_absolute_url'))

        self.assertEqual(link.get_absolute_url(), '/public-ranking/%s' % link.token)
        match = resolve(reverse('public_ranking', args=[link.token]))
        self.assertEqual(match.url_name, 'public_ranking')
        self.assertEqual(match.kwargs['token'], link.token)

    def test_public_route_validity_gate(self):
        # Feature: public-ranking-link, Property 6: Chỉ link Public và còn hiệu lực mới hiển thị.
        link = ContestPublicRankingLink.create_for(self.make_contest('public_link_gate'))
        response = self.client.get(link.get_absolute_url())
        self.assertEqual(response.status_code, 200)

        link.set_status(ContestPublicRankingLink.STATUS_PRIVATE)
        response = self.client.get(link.get_absolute_url())
        self.assertEqual(response.status_code, 404)

        link.set_status(ContestPublicRankingLink.STATUS_PUBLIC)
        link.expires_at = timezone.now() - timezone.timedelta(seconds=1)
        link.save(update_fields=['expires_at'])
        response = self.client.get(link.get_absolute_url())
        self.assertEqual(response.status_code, 404)

    def test_public_route_respects_scoreboard_visibility(self):
        contest = self.make_contest(
            'public_link_hidden_scoreboard',
            scoreboard_visibility='H',
        )
        link = ContestPublicRankingLink.create_for(contest)
        response = self.client.get(link.get_absolute_url())
        self.assertEqual(response.status_code, 404)

    def test_public_route_nonexistent_and_old_regenerated_tokens_404(self):
        # Feature: public-ranking-link, Property 7: Token không tồn tại trả về 404.
        response = self.client.get(reverse('public_ranking', args=['A' * 18]))
        self.assertEqual(response.status_code, 404)

        # Feature: public-ranking-link, Property 8: Regenerate vô hiệu hoá token cũ ở mức HTTP.
        link = ContestPublicRankingLink.create_for(self.make_contest('public_link_old_http'))
        old_url = link.get_absolute_url()
        link.regenerate()
        response = self.client.get(old_url)
        self.assertEqual(response.status_code, 404)

    def test_management_endpoints_reject_unauthorized_user(self):
        # Feature: public-ranking-link, Property 11: Thực thi phân quyền quản lý.
        contest = self.make_contest('public_link_permission')
        link = ContestPublicRankingLink.create_for(contest)
        state = (link.token, link.status, link.expiry_mode, link.expiry_amount, link.expires_at)

        self.client.force_login(self.outsider)
        endpoints = (
            ('contest_public_ranking_create', {}),
            ('contest_public_ranking_update', {
                'status': ContestPublicRankingLink.STATUS_PRIVATE,
                'expiry_mode': ContestPublicRankingLink.EXPIRY_UNLIMITED,
            }),
            ('contest_public_ranking_regenerate', {}),
        )
        for name, data in endpoints:
            with self.subTest(endpoint=name):
                response = self.client.post(reverse(name, args=[contest.key]), data=data)
                self.assertEqual(response.status_code, 403)

        link.refresh_from_db()
        self.assertEqual((link.token, link.status, link.expiry_mode, link.expiry_amount, link.expires_at), state)

    def test_management_endpoints_create_update_regenerate_and_invalid_expiry(self):
        contest = self.make_contest('public_link_manage_success')
        self.client.force_login(self.manager)

        response = self.client.post(reverse('contest_public_ranking_create', args=[contest.key]))
        self.assertEqual(response.status_code, 302)
        link = ContestPublicRankingLink.objects.get(contest=contest)
        self.assertEqual(link.status, ContestPublicRankingLink.STATUS_PUBLIC)

        response = self.client.post(reverse('contest_public_ranking_update', args=[contest.key]), data={
            'status': ContestPublicRankingLink.STATUS_PRIVATE,
            'expiry_mode': ContestPublicRankingLink.EXPIRY_MINUTES,
            'expiry_amount': '15',
        })
        self.assertEqual(response.status_code, 302)
        link.refresh_from_db()
        self.assertEqual(link.status, ContestPublicRankingLink.STATUS_PRIVATE)
        self.assertEqual(link.expiry_mode, ContestPublicRankingLink.EXPIRY_MINUTES)
        self.assertEqual(link.expiry_amount, 15)
        self.assertEqual(link.expires_at, link.regenerated_at + timezone.timedelta(minutes=15))

        before_invalid = (link.token, link.status, link.expiry_mode, link.expiry_amount, link.expires_at)
        response = self.client.post(reverse('contest_public_ranking_update', args=[contest.key]), data={
            'status': ContestPublicRankingLink.STATUS_PUBLIC,
            'expiry_mode': ContestPublicRankingLink.EXPIRY_DAYS,
            'expiry_amount': '0',
        })
        self.assertEqual(response.status_code, 302)
        link.refresh_from_db()
        self.assertEqual((link.token, link.status, link.expiry_mode, link.expiry_amount, link.expires_at),
                         before_invalid)

        expires_at_value = '2026-07-15 08:30:45'
        expected_expires_at = timezone.make_aware(
            datetime.strptime(expires_at_value, '%Y-%m-%d %H:%M:%S'),
            ZoneInfo(self.manager.profile.timezone),
        )
        response = self.client.post(reverse('contest_public_ranking_update', args=[contest.key]), data={
            'status': ContestPublicRankingLink.STATUS_PUBLIC,
            'expiry_mode': ContestPublicRankingLink.EXPIRY_DATETIME,
            'expires_at': expires_at_value,
        })
        self.assertEqual(response.status_code, 302)
        link.refresh_from_db()
        self.assertEqual(link.status, ContestPublicRankingLink.STATUS_PUBLIC)
        self.assertEqual(link.expiry_mode, ContestPublicRankingLink.EXPIRY_DATETIME)
        self.assertIsNone(link.expiry_amount)
        self.assertEqual(link.expires_at, expected_expires_at)

        before_invalid_datetime = (link.token, link.status, link.expiry_mode, link.expiry_amount, link.expires_at)
        response = self.client.post(reverse('contest_public_ranking_update', args=[contest.key]), data={
            'status': ContestPublicRankingLink.STATUS_PRIVATE,
            'expiry_mode': ContestPublicRankingLink.EXPIRY_DATETIME,
            'expires_at': 'not-a-date',
        })
        self.assertEqual(response.status_code, 302)
        link.refresh_from_db()
        self.assertEqual((link.token, link.status, link.expiry_mode, link.expiry_amount, link.expires_at),
                         before_invalid_datetime)

        old_token = link.token
        response = self.client.post(reverse('contest_public_ranking_regenerate', args=[contest.key]))
        self.assertEqual(response.status_code, 302)
        link.refresh_from_db()
        self.assertNotEqual(link.token, old_token)
        self.assertFalse(ContestPublicRankingLink.objects.filter(token=old_token).exists())
        self.assertEqual(link.expires_at, expected_expires_at)

    def test_legacy_ranking_access_code_route_still_exists(self):
        contest = self.make_contest(
            'public_link_legacy_code',
            is_private=False,
            scoreboard_visibility='V',
            ranking_access_code='legacy-secret',
        )
        new_link = ContestPublicRankingLink.create_for(contest)
        url = reverse('contest_public_ranking', args=[contest.key])
        self.assertEqual(resolve(url).url_name, 'contest_public_ranking')
        response = self.client.get(url, {'code': 'legacy-secret'})
        self.assertEqual(response.status_code, 200)
        contest.refresh_from_db()
        new_link.refresh_from_db()
        self.assertEqual(contest.ranking_access_code, 'legacy-secret')
        self.assertEqual(new_link.contest, contest)
