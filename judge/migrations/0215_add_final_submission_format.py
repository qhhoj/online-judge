# Generated manually - Add Final Submission Only contest format and Pending submission status

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0214_create_user_activity_models'),
    ]

    operations = [
        # Add 'PD' (Pending) status to Submission.status field choices
        migrations.AlterField(
            model_name='submission',
            name='status',
            field=models.CharField(
                choices=[
                    ('QU', 'Queued'),
                    ('P', 'Processing'),
                    ('G', 'Grading'),
                    ('D', 'Completed'),
                    ('IE', 'Internal Error'),
                    ('CE', 'Compile Error'),
                    ('AB', 'Aborted'),
                    ('PD', 'Pending'),
                ],
                db_index=True,
                default='QU',
                max_length=2,
                verbose_name='status',
            ),
        ),
        # Note: Contest.format_name choices are dynamically generated from contest_format.choices()
        # The new 'final_submission' format will be automatically available after importing
        # FinalSubmissionContestFormat in judge/contest_format/__init__.py
    ]

