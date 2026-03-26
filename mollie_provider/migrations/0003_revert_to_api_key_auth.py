# Revert MollieConnection from OAuth (access_token/refresh_token) back to API key auth.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mollie_provider', '0002_rename_api_key_mollieconnection_access_token_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='mollieconnection',
            name='refresh_token',
        ),
        migrations.RemoveField(
            model_name='mollieconnection',
            name='token_expires_at',
        ),
        migrations.RenameField(
            model_name='mollieconnection',
            old_name='access_token',
            new_name='api_key',
        ),
    ]
