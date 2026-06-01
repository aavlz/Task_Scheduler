from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_alter_userprofile_language_alter_userprofile_region'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='device_notifications_enabled',
            field=models.BooleanField(default=False),
        ),
    ]
