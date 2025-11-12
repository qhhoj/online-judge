from datetime import timedelta

from django.db.models import Max
from django.template.defaultfilters import floatformat
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from judge.contest_format.default import DefaultContestFormat
from judge.contest_format.registry import register_contest_format
from judge.utils.timedelta import nice_repr


@register_contest_format('final_submission')
class FinalSubmissionContestFormat(DefaultContestFormat):
    name = gettext_lazy('Final Submission Only')
    config_defaults = {
        'cumtime': False,
        'auto_judge': True,
    }
    """
        cumtime: Always False for this format. Time is not considered in scoring.
        auto_judge: If True, automatically rejudge all submissions when contest ends.
                    If False, require manual trigger from admin panel.

        This format allows multiple submissions during the contest and judges them immediately.
        Users can see results in real-time, but only the last submission for each problem is scored.
        Ranking is based purely on total score (IOI-style), with no time penalties.
        Ranking updates in real-time as submissions are judged.
    """

    @classmethod
    def validate(cls, config):
        if config is None:
            return

        if not isinstance(config, dict):
            raise ValidationError('Final Submission contest expects no config or dict as config')

        for key, value in config.items():
            if key not in cls.config_defaults:
                raise ValidationError('unknown config key "%s"' % key)
            if not isinstance(value, type(cls.config_defaults[key])):
                raise ValidationError('invalid type for config key "%s"' % key)

    def __init__(self, contest, config):
        self.config = self.config_defaults.copy()
        self.config.update(config or {})
        self.contest = contest

    def update_participation(self, participation):
        """
        Update participation score based on the last submission for each problem.
        Only considers submissions that have been judged (status is graded).
        """
        import logging
        logger = logging.getLogger('judge.contest_format.final_submission')

        score = 0
        format_data = {}

        # Get the last submission for each problem (by submission date)
        # Only consider graded submissions (exclude pending/queued/processing)
        queryset = (
            participation.submissions
            .exclude(submission__status__in=['PD', 'QU', 'P', 'G'])  # Exclude non-graded submissions
            .values('problem_id')
            .annotate(last_date=Max('submission__date'))
            .values_list('problem_id', 'last_date')
        )

        logger.info(f'Updating participation {participation.id} for contest {self.contest.key}')
        logger.info(f'Found {queryset.count()} problems with submissions')

        # For each problem, get the last submission and its points
        for problem_id, last_date in queryset:
            last_submission = (
                participation.submissions
                .filter(problem_id=problem_id, submission__date=last_date)
                .exclude(submission__status__in=['PD', 'QU', 'P', 'G'])  # Exclude non-graded
                .first()
            )

            if last_submission:
                points = last_submission.points
                logger.info(
                    f'Problem {problem_id}: last submission {last_submission.submission_id} '
                    f'(date: {last_date}, status: {last_submission.submission.status}, '
                    f'points: {points})'
                )
                format_data[str(problem_id)] = {
                    'points': points,
                    'time': 0,  # Time is not considered
                }
                score += points

        logger.info(f'Total score: {score}, format_data: {format_data}')

        participation.cumtime = 0  # No time penalty
        participation.score = round(score, self.contest.points_precision)
        participation.tiebreaker = 0  # No tiebreaker
        participation.format_data = format_data
        participation.save()

        logger.info(f'Saved participation: score={participation.score}, format_data={participation.format_data}')

    def get_first_solves_and_total_ac(self, problems, participations, frozen=False):
        """
        Get first solves and total AC for each problem.
        Since time is not considered, first solve is not meaningful, but we implement it for compatibility.
        """
        first_solves = {}
        total_ac = {}

        for problem in problems:
            problem_id = str(problem.id)
            first_solves[problem_id] = None
            total_ac[problem_id] = 0

            for participation in participations:
                format_data = (participation.format_data or {}).get(problem_id)
                if format_data:
                    points = format_data['points']
                    if points == problem.points:
                        total_ac[problem_id] += 1

        return first_solves, total_ac

    def display_user_problem(self, participation, contest_problem, first_solves, frozen=False):
        """
        Display user's score for a specific problem.
        Shows only points, no time information.
        """
        format_data = (participation.format_data or {}).get(str(contest_problem.id))
        if format_data:
            return format_html(
                '<td class="{state}"><a href="{url}">{points}</a></td>',
                state=(
                    ('pretest-' if self.contest.run_pretests_only and contest_problem.is_pretested else '') +
                    self.best_solution_state(format_data['points'], contest_problem.points)
                ),
                url=reverse(
                    'contest_user_submissions',
                    args=[self.contest.key, participation.user.user.username, contest_problem.problem.code],
                ),
                points=floatformat(format_data['points'], -self.contest.points_precision),
            )
        else:
            return mark_safe('<td></td>')

    def display_participation_result(self, participation, frozen=False):
        """
        Display participation result (total score).
        No time information is shown.
        """
        return format_html(
            '<td class="user-points"><a href="{url}">{points}</a></td>',
            url=reverse(
                'contest_all_user_submissions',
                args=[self.contest.key, participation.user.user.username],
            ),
            points=floatformat(participation.score, -self.contest.points_precision),
        )

    def get_short_form_display(self):
        """
        Display format description in contest settings.
        """
        yield _('Chế độ cho nộp bài nhiều lần, chấm điểm ngay và tính điểm cho lần nộp cuối cùng.')
        yield _('Submissions are judged immediately during the contest.')
        yield _('Users can see results in real-time.')
        yield _('Only the last submission for each problem is scored.')
        yield _('Ranking updates in real-time and is based purely on total score, with no time penalties.')
        yield _('Ties by score will **not** be broken.')
        yield ''
        yield _('Configuration options:')
        yield _('- auto_judge: true (default) = Automatically rejudge all submissions when contest ends')
        yield _('- auto_judge: false = No automatic rejudge')
        yield _('Example: {"auto_judge": false}')

