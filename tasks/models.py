from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

# Create your models here.
class Task(models.Model):
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tasks')
    category = models.ForeignKey(
        'TaskCategory',
        on_delete=models.SET_NULL,
        related_name='tasks',
        blank=True,
        null=True,
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    date = models.DateField()
    time = models.TimeField(blank=True, null=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    reminder_minutes_before = models.PositiveIntegerField(default=10)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['date', 'time']
        indexes = [
            models.Index(fields=['user', 'date']),
            models.Index(fields=['user', 'status']),
            models.Index(fields=['user', 'priority']),
            models.Index(fields=['user', 'created_at']),
        ]

    def __str__(self):
        return f"{self.title} ({self.date}{self.time})"
    
    @property
    def is_overdue(self):
        """Return True if task is not completed and its scheduled datetime is strictly less than now.

        Handles tasks with date only (no time) and date+time. If time is missing, compare by date only
        (task is overdue if date < today). If time exists, compare full aware datetime.
        """
        if self.status == 'completed':
            return False

        now = timezone.now()

        # If no date set, cannot be overdue
        if not self.date:
            return False

        # If time is not provided, evaluate by date only
        if not self.time:
            return self.date < timezone.localdate()

        # Combine date and time into aware datetime safely
        dt = timezone.datetime.combine(self.date, self.time)
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())

        return dt < now


class TaskCategory(models.Model):
    ALLOWED_NAMES = ['School', 'Work', 'Personal', 'Others']
    DEFAULT_COLORS = {
        'School': '#338A85',
        'Work': '#3B82F6',
        'Personal': '#A855F7',
        'Others': '#64748B',
    }

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='task_categories')
    name = models.CharField(max_length=80)
    color = models.CharField(max_length=7, default='#338A85')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(fields=['user', 'name'], name='unique_task_category_per_user')
        ]

    def __str__(self):
        return self.name


class TaskReminder(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='reminders')
    remind_at = models.DateTimeField()
    delivered = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['remind_at']
