from datetime import timedelta

from django.template.defaultfilters import floatformat
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _, gettext_lazy

from judge.contest_format.legacy_ioi import LegacyIOIContestFormat
from judge.contest_format.registry import register_contest_format
from judge.utils.timedelta import nice_repr
from judge.timezone import from_database_time


@register_contest_format('ioi16')
class IOIContestFormat(LegacyIOIContestFormat):
    name = gettext_lazy('IOI')
    config_defaults = {'cumtime': False}
    """
        cumtime: Specify True if time penalties are to be computed. Defaults to False.
    """

    def update_participation(self, participation):
        cumtime = 0
        score = 0
        public_score = 0
        hidden_score = 0
        format_data = {}

        problem_subtask_data = participation.get_best_subtask_point()

        from judge.models.contest import ContestProblem

        for problem_id, subtask_data in problem_subtask_data.items():
            cp = ContestProblem.objects.filter(id=problem_id, contest=self.contest).first()
            scale = cp.points_scaling_factor
            for index, batch in enumerate(subtask_data):
                subtask_data[batch] *= scale
            points = sum(subtask_data.values())
            hidden_points = 0
            have_hidden_subtasks = 0
            for batch in cp.get_hidden_subtasks():
                if subtask_data.get(batch) is not None:
                    hidden_points += subtask_data[batch]
                    have_hidden_subtasks = True
            public_points = points - hidden_points
            format_data[problem_id] = {
                'points' : points,
                'frozen_points': public_points,
                'have_hidden_subtasks': have_hidden_subtasks,
                'time' : 0,
            }
            score += points
            hidden_score += hidden_points
            public_score += public_points

        participation.cumtime = max(cumtime, 0)
        participation.score = round(score, self.contest.points_precision)
        participation.frozen_score = round(public_score, self.contest.points_precision)
        participation.tiebreaker = 0
        participation.format_data = format_data
        participation.save()

    def get_first_solves_and_total_ac(self, problems, participations, frozen=False):
        return {}, {}

    def display_user_problem(self, participation, contest_problem, first_solves, frozen=False):
        format_data = (participation.format_data or {}).get(str(contest_problem.id))

        if format_data:
            if not frozen:
                return format_html(
                    '<td class="{state}"><a href="{url}">{points}<div class="solving-time">{time}</div></a></td>',
                    state=(('pretest-' if self.contest.run_pretests_only and contest_problem.is_pretested else '') +
                           ('first-solve ' if first_solves.get(str(contest_problem.id), None) == participation.id else '') +
                           self.best_solution_state(format_data['points'], contest_problem.points)),
                    url=reverse('contest_user_submissions',
                                args=[self.contest.key, participation.user.user.username, contest_problem.problem.code]),
                    points=str(floatformat(format_data['points'], -self.contest.points_precision)),
                    time=nice_repr(timedelta(seconds=format_data['time']), 'noday'),
                )

            return format_html(
                '<td class="{state}"><a href="{url}">{points}<div class="solving-time">{time}</div></a></td>',
                state=(('pretest-' if self.contest.run_pretests_only and contest_problem.is_pretested else '') +
                       ('first-solve ' if first_solves.get(str(contest_problem.id), None) == participation.id else '') +
                       self.best_solution_state(format_data['frozen_points'], contest_problem.points)),
                url=reverse('contest_user_submissions',
                            args=[self.contest.key, participation.user.user.username, contest_problem.problem.code]),
                points=(
                    str(floatformat(format_data['frozen_points'], -self.contest.points_precision)) + 
                    ('+???' if format_data['have_hidden_subtasks'] else '')
                ),
                time=nice_repr(timedelta(seconds=format_data['time']), 'noday'),
            )
        else:
            return mark_safe('<td></td>')

    def display_participation_result(self, participation, frozen=False):
        return format_html(
            '<td class="user-points"><a href="{url}">{points}<div class="solving-time">{cumtime}</div></a></td>',
            url=reverse('contest_all_user_submissions',
                        args=[self.contest.key, participation.user.user.username]),
            points=floatformat(
                participation.frozen_score if frozen else participation.score, -self.contest.points_precision
            ),
            cumtime=nice_repr(timedelta(seconds=participation.cumtime), 'noday'),
        )

    def get_short_form_display(self):
        yield _('The maximum score for each problem batch will be used.')

        if self.config['cumtime']:
            yield _('Ties will be broken by the sum of the last score altering submission time on problems with a '
                    'non-zero score.')
        else:
            yield _('Ties by score will **not** be broken.')
