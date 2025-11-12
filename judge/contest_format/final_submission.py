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
        auto_judge: If True, automatically judge submissions when contest ends.
                    If False, require manual trigger from admin panel.

        This format allows multiple submissions during the contest, but only judges them
        after the contest ends. Only the last submission for each problem is scored.
        Ranking is based purely on total score (IOI-style), with no time penalties.
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
        Only considers submissions that have been judged (not in pending state).
        """
        from django.db.models import OuterRef, Subquery
        import logging
        logger = logging.getLogger('judge.contest_format.final_submission')

        score = 0
        format_data = {}

        # Debug: Log all submissions for this participation
        all_subs = participation.submissions.all()
        logger.info(f'[FSO] Participation {participation.id}: Total submissions = {all_subs.count()}')
        for sub in all_subs:
            logger.info(
                f'[FSO]   Sub {sub.submission_id}: problem={sub.problem_id}, '
                f'date={sub.submission.date}, status={sub.submission.status}, points={sub.points}'
            )

        # Get the last submission for each problem (by submission date)
        # Similar to Ultimate format but exclude PD status
        queryset = (
            participation.submissions
            .exclude(submission__status='PD')
            .values('problem_id')
            .filter(
                submission__date=Subquery(
                    participation.submissions
                    .exclude(submission__status='PD')
                    .filter(problem_id=OuterRef('problem_id'))
                    .order_by('-submission__date')
                    .values('submission__date')[:1]
                )
            )
            .values_list('problem_id', 'points')
        )

        logger.info(f'[FSO] Queryset count = {queryset.count()}')

        # Calculate score from last submissions
        for problem_id, points in queryset:
            logger.info(f'[FSO] Problem {problem_id}: points = {points}')
            format_data[str(problem_id)] = {
                'points': points,
                'time': 0,  # Time is not considered
            }
            score += points

        logger.info(f'[FSO] Total score = {score}, format_data = {format_data}')

        participation.cumtime = 0  # No time penalty
        participation.score = round(score, self.contest.points_precision)
        participation.tiebreaker = 0  # No tiebreaker
        participation.format_data = format_data
        participation.save()

        logger.info(f'[FSO] Saved: participation.score = {participation.score}')

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
        yield _('Chế độ cho nộp bài nhiều lần, cuối giờ chấm điểm và tính điểm cho lần nộp cuối cùng.')
        yield _('Submissions are not judged during the contest.')
        yield _('After the contest ends, only the last submission for each problem will be judged and scored.')
        yield _('Ranking is based purely on total score, with no time penalties.')
        yield _('Ties by score will **not** be broken.')
        yield ''
        yield _('Configuration options:')
        yield _('- auto_judge: true (default) = Automatically judge when contest ends')
        yield _('- auto_judge: false = Require manual judge trigger from admin panel')
        yield _('Example: {"auto_judge": false}')

