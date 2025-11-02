from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from judge.models import (
    UserActivity,
    UserSession,
)


class Command(BaseCommand):
    help = 'Check user activity tracking status'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=== USER ACTIVITY TRACKING STATUS ===\n'))

        # Check total sessions
        total_sessions = UserSession.objects.count()
        self.stdout.write(f'Total sessions in database: {total_sessions}')

        # Check active sessions (last 30 minutes)
        cutoff_time = timezone.now() - timedelta(minutes=30)
        active_sessions = UserSession.objects.filter(
            last_activity__gte=cutoff_time,
            is_active=True,
        )

        self.stdout.write(f'Active sessions (last 30 min): {active_sessions.count()}')

        # Breakdown by device type
        self.stdout.write('\n=== BREAKDOWN BY DEVICE TYPE ===')
        for device_type in ['desktop', 'mobile', 'tablet', 'bot', 'unknown']:
            count = active_sessions.filter(device_type=device_type).count()
            self.stdout.write(f'  {device_type}: {count}')

        # Breakdown by authentication
        self.stdout.write('\n=== BREAKDOWN BY AUTHENTICATION ===')
        authenticated = active_sessions.filter(user__isnull=False).count()
        anonymous = active_sessions.filter(user__isnull=True).count()
        self.stdout.write(f'  Authenticated: {authenticated}')
        self.stdout.write(f'  Anonymous: {anonymous}')

        # Bot breakdown
        bot_sessions = active_sessions.filter(device_type='bot')
        self.stdout.write('\n=== BOT SESSIONS ===')
        self.stdout.write(f'  Total bots: {bot_sessions.count()}')
        self.stdout.write(f'  Bot authenticated: {bot_sessions.filter(user__isnull=False).count()}')
        self.stdout.write(f'  Bot anonymous: {bot_sessions.filter(user__isnull=True).count()}')

        # Recent activities
        recent_activities = UserActivity.objects.filter(
            timestamp__gte=cutoff_time,
        ).count()
        self.stdout.write(f'\n=== RECENT ACTIVITIES ===')
        self.stdout.write(f'Total activities (last 30 min): {recent_activities}')

        # Latest sessions
        self.stdout.write('\n=== LATEST 10 SESSIONS ===')
        latest_sessions = UserSession.objects.all()[:10]
        for session in latest_sessions:
            user_str = session.user.username if session.user else 'Anonymous'
            self.stdout.write(
                f'  {user_str} | {session.device_type} | {session.ip_address} | '
                f'{session.last_activity.strftime("%Y-%m-%d %H:%M:%S")}',
            )

        self.stdout.write(self.style.SUCCESS('\n=== CHECK COMPLETE ==='))

