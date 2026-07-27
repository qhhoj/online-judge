"""
Management command to check and trigger judging for ended FSO contests.
Can be run via cron job every minute for immediate judging.

Usage:
    python manage.py check_fso_contests
    python manage.py check_fso_contests --force --contest <key>

Cron example (run every minute):
    * * * * * cd /path/to/site && python manage.py check_fso_contests >> /var/log/fso_check.log 2>&1

Each contest is judged at most once per end time. The claim is recorded in the database
(Contest.fso_judged_end_time), so it holds across processes and restarts -- a fresh process from
cron will not re-judge a contest that has already been handled.
"""
from django.core.management.base import BaseCommand
from django.db.models import F
from django.utils import timezone

from judge.models import Contest


class Command(BaseCommand):
    help = 'Check for ended FSO contests and trigger judging'

    def add_arguments(self, parser):
        parser.add_argument(
            '--contest', help='only consider the contest with this key',
        )
        parser.add_argument(
            '--force', action='store_true',
            help='judge even if this contest has already been judged for its current end time. '
                 'Does not reset already-judged submissions unless --rejudge-all is also given.',
        )
        parser.add_argument(
            '--rejudge-all', action='store_true',
            help='reset and rejudge every submission in the contest, not just unjudged ones. '
                 'Destructive: discards existing test case results.',
        )

    def handle(self, *args, **options):
        from judge.tasks.contest import _judge_final_submissions_impl

        force = options['force']
        rejudge_all = options['rejudge_all']

        contests = Contest.objects.filter(
            format_name='final_submission',
            end_time__lte=timezone.now(),
        )
        if options['contest']:
            contests = contests.filter(key=options['contest'])
        if not force:
            contests = contests.exclude(fso_judged_end_time=F('end_time'))

        processed_count = 0
        for contest in contests:
            if not force and not contest.is_fso_auto_judge_pending():
                continue

            # Atomic claim. Without --force this is what makes repeated cron runs a no-op.
            claimed = contest.claim_fso_auto_judge()
            if not claimed and not force:
                continue

            self.stdout.write(self.style.SUCCESS(f'✓ Judging contest {contest.key}'))
            try:
                result = _judge_final_submissions_impl(contest.key, rejudge_all=rejudge_all)
                self.stdout.write(f'  {result.get("message", "completed")}')
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  Error: {e}'))
                import traceback
                traceback.print_exc()

            processed_count += 1

        if processed_count > 0:
            self.stdout.write(self.style.SUCCESS(f'✓ Processed {processed_count} contests'))
