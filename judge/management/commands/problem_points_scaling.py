from django.core.management.base import BaseCommand

from judge.models import Problem


def rescale(x) -> int:
    if 0 <= x and x <= 2:
        return round(x * 1350 + 800)
    return x


class Command(BaseCommand):
    help = 'Change problem points distribution from 0.0 - 2.0 to 800 - 3500'

    def add_arguments(self, *args, **options) -> None:
        pass

    def handle(self, *args, **options) -> None:
        problems = Problem.objects.all()
        for problem in problems:
            problem.points = rescale(problem.points)
            problem.save()
