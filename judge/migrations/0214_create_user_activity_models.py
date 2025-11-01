# Generated manually - Create UserSession and UserActivity models
# These models are used for tracking user activity and sessions

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('judge', '0213_alter_profile_timezone'),
    ]

    operations = [
        # Create UserSession model
        migrations.CreateModel(
            name='UserSession',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('session_key', models.CharField(max_length=40, unique=True)),
                ('ip_address', models.GenericIPAddressField(verbose_name='IP address')),
                ('user_agent', models.TextField(verbose_name='user agent')),
                ('device_type', models.CharField(
                    choices=[
                        ('desktop', 'Desktop'),
                        ('mobile', 'Mobile'),
                        ('tablet', 'Tablet'),
                        ('bot', 'Bot'),
                        ('unknown', 'Unknown')
                    ],
                    default='unknown',
                    max_length=20,
                    verbose_name='device type'
                )),
                ('browser', models.CharField(blank=True, max_length=50, verbose_name='browser')),
                ('os', models.CharField(blank=True, max_length=50, verbose_name='operating system')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='created at')),
                ('last_activity', models.DateTimeField(default=django.utils.timezone.now, verbose_name='last activity')),
                ('is_active', models.BooleanField(default=True, verbose_name='is active')),
                ('user', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='user_sessions',
                    to=settings.AUTH_USER_MODEL
                )),
            ],
            options={
                'verbose_name': 'user session',
                'verbose_name_plural': 'user sessions',
                'ordering': ['-last_activity'],
                'indexes': [
                    # Index cho query active sessions (most common query)
                    models.Index(fields=['last_activity', 'is_active'], name='judge_users_last_ac_idx'),
                    # Index cho query sessions by user
                    models.Index(fields=['user', '-last_activity'], name='judge_users_user_la_idx'),
                    # Index cho filter by device_type
                    models.Index(fields=['device_type', '-last_activity'], name='judge_users_device_idx'),
                    # Index cho query active sessions by device type
                    models.Index(fields=['is_active', 'device_type', '-last_activity'], name='judge_users_active_idx'),
                ],
            },
        ),
        
        # Create UserActivity model
        migrations.CreateModel(
            name='UserActivity',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('timestamp', models.DateTimeField(auto_now_add=True, verbose_name='timestamp')),
                ('path', models.CharField(max_length=500, verbose_name='path')),
                ('method', models.CharField(default='GET', max_length=10, verbose_name='HTTP method')),
                ('ip_address', models.GenericIPAddressField(verbose_name='IP address')),
                ('user_agent', models.TextField(blank=True, verbose_name='user agent')),
                ('referer', models.TextField(blank=True, verbose_name='referer')),
                ('response_code', models.IntegerField(blank=True, null=True, verbose_name='response code')),
                ('user', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='activities',
                    to=settings.AUTH_USER_MODEL
                )),
                ('session', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to='judge.UserSession'
                )),
            ],
            options={
                'verbose_name': 'user activity',
                'verbose_name_plural': 'user activities',
                'ordering': ['-timestamp'],
                'indexes': [
                    models.Index(fields=['user', '-timestamp'], name='judge_usera_user_id_idx'),
                    models.Index(fields=['timestamp'], name='judge_usera_timesta_idx'),
                    models.Index(fields=['ip_address', '-timestamp'], name='judge_usera_ip_addr_idx'),
                ],
            },
        ),
    ]

