# Generated by Django 3.2.25 on 2024-05-07 15:39

import django.core.validators
from django.db import migrations, models

import judge.models.problem_data
import judge.utils.problem_data


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0206_alter_contest_format_name'),
    ]

    operations = [
        migrations.AlterField(
            model_name='problemdata',
            name='custom_checker',
            field=models.FileField(blank=True, null=True, storage=judge.utils.problem_data.ProblemDataStorage(), upload_to=judge.models.problem_data.problem_directory_file, validators=[django.core.validators.FileExtensionValidator(allowed_extensions=['cpp', 'pas', 'java', 'py'])], verbose_name='custom checker file'),
        ),
    ]
