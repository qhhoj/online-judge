# Generated for qhhoj-vjudge-integration.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0216_problem_mirroring'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExternalJudgeConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True, verbose_name='name')),
                ('base_url', models.URLField(help_text='PCD VJudge API base URL, e.g. https://vjudge.example.com', verbose_name='base URL')),
                ('encrypted_api_token', models.TextField(verbose_name='encrypted API token')),
                ('token_prefix', models.CharField(blank=True, max_length=20, verbose_name='token prefix')),
                ('is_active', models.BooleanField(default=True, verbose_name='is active')),
                ('timeout_seconds', models.PositiveIntegerField(default=30, verbose_name='submit timeout seconds')),
                ('poll_timeout_seconds', models.PositiveIntegerField(default=10, verbose_name='poll timeout seconds')),
                ('poll_interval_seconds', models.PositiveIntegerField(default=5, verbose_name='poll interval seconds')),
                ('max_poll_attempts', models.PositiveIntegerField(default=120, verbose_name='max poll attempts')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('last_verified_at', models.DateTimeField(blank=True, null=True, verbose_name='last verified at')),
            ],
            options={
                'verbose_name': 'External Judge Configuration',
                'verbose_name_plural': 'External Judge Configurations',
            },
        ),
        migrations.CreateModel(
            name='ExternalProblem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('oj', models.CharField(max_length=50, verbose_name='OJ identifier')),
                ('external_problem_id', models.CharField(max_length=100, verbose_name='external problem ID')),
                ('is_active', models.BooleanField(default=True, verbose_name='is active')),
                ('metadata_cache', models.JSONField(blank=True, default=dict, verbose_name='metadata cache')),
                ('language_mappings', models.JSONField(blank=True, default=list, verbose_name='language mappings')),
                ('last_synced_at', models.DateTimeField(blank=True, null=True, verbose_name='last synced at')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('config', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='problems', to='judge.externaljudgeconfig', verbose_name='configuration')),
                ('problem', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='external_problem', to='judge.problem', verbose_name='problem')),
            ],
            options={
                'verbose_name': 'External Problem',
                'verbose_name_plural': 'External Problems',
            },
        ),
        migrations.CreateModel(
            name='ExternalSubmission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('pcd_submission_id', models.UUIDField(verbose_name='PCD submission ID')),
                ('pcd_system_status', models.CharField(default='pending', max_length=30, verbose_name='PCD system status')),
                ('pcd_status_canonical', models.CharField(blank=True, max_length=30, null=True, verbose_name='PCD canonical status')),
                ('pcd_vjudge_run_id', models.CharField(blank=True, max_length=100, null=True, verbose_name='VJudge run ID')),
                ('pcd_remote_url', models.URLField(blank=True, max_length=1000, null=True, verbose_name='remote URL')),
                ('pcd_runtime_ms', models.IntegerField(blank=True, null=True, verbose_name='runtime milliseconds')),
                ('pcd_memory_kb', models.IntegerField(blank=True, null=True, verbose_name='memory KB')),
                ('pcd_score_text', models.CharField(blank=True, max_length=100, null=True, verbose_name='score text')),
                ('last_polled_at', models.DateTimeField(blank=True, null=True, verbose_name='last polled at')),
                ('poll_attempts', models.PositiveIntegerField(default=0, verbose_name='poll attempts')),
                ('raw_response', models.JSONField(blank=True, default=dict, verbose_name='raw response')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('config', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='judge.externaljudgeconfig', verbose_name='configuration')),
                ('submission', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='external_submission', to='judge.submission', verbose_name='submission')),
            ],
            options={
                'verbose_name': 'External Submission',
                'verbose_name_plural': 'External Submissions',
            },
        ),
        migrations.AddIndex(
            model_name='externalproblem',
            index=models.Index(fields=['config', 'oj', 'external_problem_id'], name='judge_exter_config__de795d_idx'),
        ),
    ]
