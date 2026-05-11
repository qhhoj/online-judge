from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('judge', '0215_add_final_submission_format'),
    ]

    operations = [
        migrations.AddField(
            model_name='problem',
            name='mirror_of',
            field=models.ForeignKey(
                blank=True,
                help_text="Use another problem's test archive while keeping this problem's own config/init.yml.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='direct_mirrors',
                to='judge.problem',
                verbose_name='mirror test data from',
            ),
        ),
        migrations.AddField(
            model_name='problem',
            name='mirror_root',
            field=models.ForeignKey(
                blank=True,
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='all_mirrors',
                to='judge.problem',
                verbose_name='mirror root problem',
            ),
        ),
    ]
