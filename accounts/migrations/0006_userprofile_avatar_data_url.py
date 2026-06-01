from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_userprofile_device_notifications_enabled'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='avatar_data_url',
            field=models.TextField(blank=True, default=''),
        ),
    ]