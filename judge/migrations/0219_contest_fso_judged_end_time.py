from django.db import (
    migrations,
    models,
)
from django.db.models import F
from django.utils import timezone


def backfill_fso_judged(apps, schema_editor):
    """
    Treat every Final Submission Only contest that has already ended as already auto-judged.

    Without this, the new marker would be NULL everywhere and the first run of the periodic check
    after deploying would claim -- and therefore mass-rejudge -- every historical FSO contest at
    once. Those contests have already been judged (repeatedly, which is the bug this migration is
    part of fixing), so the correct starting state is "done".

    Contests that have not ended yet are left NULL so they are judged normally when they end.
    """
    Contest = apps.get_model('judge', 'Contest')
    Contest.objects.filter(
        format_name='final_submission',
        end_time__lte=timezone.now(),
    ).update(fso_judged_end_time=F('end_time'))


def unset_fso_judged(apps, schema_editor):
    Contest = apps.get_model('judge', 'Contest')
    Contest.objects.filter(format_name='final_submission').update(fso_judged_end_time=None)


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0218_contestpublicrankinglink'),
    ]

    operations = [
        migrations.AddField(
            model_name='contest',
            name='fso_judged_end_time',
            field=models.DateTimeField(
                blank=True,
                default=None,
                help_text='The end time for which Final Submission Only automatic judging has '
                          'already been triggered. Cleared implicitly when the contest end time '
                          'changes, so extending a contest re-arms judging.',
                null=True,
                verbose_name='FSO auto-judge marker',
            ),
        ),
        migrations.RunPython(backfill_fso_judged, unset_fso_judged),
    ]
