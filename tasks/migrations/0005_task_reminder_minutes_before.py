from django.db import migrations, models
from django.utils import timezone
from datetime import datetime, timedelta


def create_default_reminders(apps, schema_editor):
    Task = apps.get_model('tasks', 'Task')
    TaskReminder = apps.get_model('tasks', 'TaskReminder')
    for task in Task.objects.exclude(time__isnull=True):
        scheduled = datetime.combine(task.date, task.time)
        if timezone.is_naive(scheduled):
            scheduled = timezone.make_aware(scheduled, timezone.get_current_timezone())
        TaskReminder.objects.get_or_create(
            task=task,
            defaults={'remind_at': scheduled - timedelta(minutes=10), 'delivered': False},
        )


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0004_alter_task_time'),
    ]

    operations = [
        migrations.AddField(
            model_name='task',
            name='reminder_minutes_before',
            field=models.PositiveIntegerField(default=10),
        ),
        migrations.RunPython(create_default_reminders, migrations.RunPython.noop),
    ]
