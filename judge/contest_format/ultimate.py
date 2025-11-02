from django.core.exceptions import ValidationError
from django.db.models import (
    OuterRef,
    Subquery
)
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from judge.contest_format import DefaultContestFormat
from judge.contest_format.registry import register_contest_format


@register_contest_format('Ultimate')
class UltimateContestFormat(DefaultContestFormat):
    name = gettext_lazy('Ultimate')

    @classmethod
    def validate(cls, config):
        if config is not None or config:
            raise ValidationError('Ultimate contest expects no config')

    def __init__(self, contest, config):
        self.config = config
        self.contest = contest

    def update_participation(self, participation):
        cumtime = 0
        last_submission_time = 0
        score = 0
        format_data = {}
        queryset = (participation.submissions.values('problem_id')
                                             .filter(submission__date=Subquery(
                                                 participation.submissions.filter(problem_id=OuterRef('problem_id'))
                                                                          .order_by('-submission__date')
                                                                          .values('submission__date')[:1]))
                                             .values_list('problem_id', 'submission__date', 'points'))

        for problem_id, time, points in queryset:
            if points:
                dt = (time - self.contest.start_time).total_seconds()
                cumtime += dt
                last_submission_time = max(last_submission_time, dt)
            else:
                dt = 0

            format_data[str(problem_id)] = {'points': points, 'time': dt}
            score += points

        participation.cumtime = max(cumtime, 0)
        participation.score = score
        participation.tiebreak = last_submission_time
        participation.format_data = format_data
        participation.save()

    def get_first_solve_and_total_ac(self, problems, participations, frozen=False):
        first_solve = {}
        total_ac = {}

        for problem in problems:
            problem_id = str(problem)
            min_time = None
            first_solve[problem_id] = None
            total_ac[problem_id] = 0

            for participation in participations:
                format_data = (participation.format_data or {}).get(problem_id)
                points = format_data['points']
                time = format_data['time']

                if points == problem.points:
                    total_ac[problem_id] += 1

                if participation.virtual == 0 and (min_time is None or min_time > time):
                    min_time = time
                    first_solve[problem_id] = participation.id

        return first_solve, total_ac

    def get_short_form_display(self):
        yield _('The last submission score for each problem will be used.')
        yield _('Ties will be broken by the sum of the last submission time for each problem.')
