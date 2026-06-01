# Generated for V.A.S.T. voice command tracking.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='VoiceAnalytics',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('total_commands', models.PositiveIntegerField(default=0)),
                ('successful_commands', models.PositiveIntegerField(default=0)),
                ('last_command_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='voice_analytics', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='VoiceCommand',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('transcript', models.TextField()),
                ('intent', models.CharField(max_length=64)),
                ('confidence', models.FloatField(default=0)),
                ('action', models.CharField(blank=True, max_length=64)),
                ('response_message', models.TextField(blank=True)),
                ('success', models.BooleanField(default=False)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='voice_commands', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.AddIndex(
            model_name='voicecommand',
            index=models.Index(fields=['user', 'created_at'], name='voice_parse_user_id_7b2a72_idx'),
        ),
        migrations.AddIndex(
            model_name='voicecommand',
            index=models.Index(fields=['intent'], name='voice_parse_intent_9dfc83_idx'),
        ),
    ]
