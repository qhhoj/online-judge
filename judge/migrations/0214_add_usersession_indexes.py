# Generated manually for performance optimization
# Adds indexes to UserSession model to improve query performance

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0213_alter_profile_timezone'),
    ]

    operations = [
        # Index cho query active sessions (most common query)
        # Sử dụng trong: UserSession.objects.filter(last_activity__gte=cutoff_time, is_active=True)
        migrations.AddIndex(
            model_name='usersession',
            index=models.Index(fields=['last_activity', 'is_active'], name='judge_users_last_ac_idx'),
        ),
        
        # Index cho query sessions by user
        # Sử dụng trong: UserSession.objects.filter(user=user).order_by('-last_activity')
        migrations.AddIndex(
            model_name='usersession',
            index=models.Index(fields=['user', '-last_activity'], name='judge_users_user_la_idx'),
        ),
        
        # Index cho filter by device_type
        # Sử dụng trong: sessions.filter(device_type='bot')
        migrations.AddIndex(
            model_name='usersession',
            index=models.Index(fields=['device_type', '-last_activity'], name='judge_users_device_idx'),
        ),
        
        # Index cho query active sessions by device type
        # Sử dụng trong: UserSession.objects.filter(is_active=True, device_type='bot')
        migrations.AddIndex(
            model_name='usersession',
            index=models.Index(fields=['is_active', 'device_type', '-last_activity'], name='judge_users_active_idx'),
        ),
    ]
