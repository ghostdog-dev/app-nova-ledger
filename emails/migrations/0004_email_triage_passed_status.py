from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('emails', '0003_add_cancellation_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='email',
            name='status',
            field=models.CharField(
                choices=[
                    ('new', 'New'),
                    ('triage_passed', 'Triage Passed'),
                    ('processed', 'Processed'),
                    ('ignored', 'Ignored'),
                ],
                default='new',
                max_length=20,
            ),
        ),
    ]
