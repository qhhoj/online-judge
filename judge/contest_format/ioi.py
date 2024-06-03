from django.utils.translation import gettext as _, gettext_lazy

from judge.contest_format.legacy_ioi import LegacyIOIContestFormat
from judge.contest_format.registry import register_contest_format
# from judge.timezone import from_database_time


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
        format_data = {}

        problem_subtask_data = participation.get_best_subtask_point()

        from judge.models.contest import ContestProblem

        for problem_id, subtask_data in problem_subtask_data.items():
            cp = ContestProblem.objects.filter(id=problem_id, contest=self.contest).first()
            scale = cp.points_scaling_factor
            for index, batch in enumerate(subtask_data):
                subtask_data[batch] *= scale
            points = sum(subtask_data.values())
            format_data[problem_id] = {
                'points': points,
                'time': 0,
            }
            score += points

        participation.cumtime = max(cumtime, 0)
        participation.score = round(score, self.contest.points_precision)
        participation.tiebreaker = 0
        participation.format_data = format_data
        participation.save()

    def get_short_form_display(self):
        yield _('The maximum score for each problem batch will be used.')

        if self.config['cumtime']:
            yield _('Ties will be broken by the sum of the last score altering submission time on problems with a '
                    'non-zero score.')
        else:
            yield _('Ties by score will **not** be broken.')
