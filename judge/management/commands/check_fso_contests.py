"""
Management command to check and trigger judging for ended FSO contests.
Can be run via cron job every minute for immediate judging.

Usage:
    python manage.py check_fso_contests
    
Cron example (run every minute):
    * * * * * cd /path/to/site && python manage.py check_fso_contests >> /var/log/fso_check.log 2>&1
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.core.cache import cache

from judge.models import Contest, Submission


class Command(BaseCommand):
    help = 'Check for ended FSO contests and trigger judging'

    def handle(self, *args, **options):
        from judge.tasks.contest import _judge_final_submissions_impl

        self.stdout.write(f'[{timezone.now()}] Checking FSO contests...')

        # Find all final_submission contests that have ended
        now = timezone.now()
        ended_contests = Contest.objects.filter(
            format_name='final_submission',
            end_time__lte=now,
        )

        self.stdout.write(f'Found {ended_contests.count()} ended FSO contests')

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

            # Check if there are any submissions
            total_count = Submission.objects.filter(
                contest__participation__contest=contest,
            ).count()

            if total_count > 0:
                # Mark as triggered (cache for 24 hours)
                cache.set(cache_key, True, 86400)

                # Trigger judging for this contest
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✓ Judging contest {contest.key} ({total_count} submissions)'
                    )
                )

                # Call the implementation directly (synchronous)
                # This is faster and doesn't require Celery worker
                try:
                    result = _judge_final_submissions_impl(contest.key, rejudge_all=False)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'  {result.get("message", "completed")}'
                        )
                    )
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f'  Error: {str(e)}'
                        )
                    )
                    import traceback
                    traceback.print_exc()

                processed_count += 1

        if processed_count > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ Processed {processed_count} contests'
                )
            )
        else:
            self.stdout.write('No contests to process')

