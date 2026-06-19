from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ('judge', '0217_external_judge'),
    ]

    operations = [
        migrations.CreateModel(
            name='ContestPublicRankingLink',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token', models.CharField(db_index=True, max_length=18, unique=True, verbose_name='token')),
                ('status', models.CharField(choices=[('public', 'Public'), ('private', 'Private')], default='public', max_length=8, verbose_name='status')),
                ('expiry_mode', models.CharField(choices=[('U', 'Never expires'), ('M', 'Expires after minutes'), ('D', 'Expires after days'), ('A', 'Expires at date/time')], default='U', max_length=1, verbose_name='expiry mode')),
                ('expiry_amount', models.PositiveIntegerField(blank=True, null=True, verbose_name='expiry amount')),
                ('expires_at', models.DateTimeField(blank=True, null=True, verbose_name='expires at')),
                ('regenerated_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='regenerated at')),
                ('contest', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='public_ranking_link', to='judge.contest', verbose_name='contest')),
            ],
            options={
                'verbose_name': 'contest public ranking link',
                'verbose_name_plural': 'contest public ranking links',
            },
        ),
    ]
