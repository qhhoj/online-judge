# Generated by Django 3.2.23 on 2024-04-23 15:00

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0203_alter_profile_timezone'),
    ]

    operations = [
        migrations.AddField(
            model_name='problem',
            name='problem_material',
            field=models.CharField(blank=True, help_text="URL to this problem's contest materials.", max_length=200, verbose_name='problem material URL'),
        ),
    ]