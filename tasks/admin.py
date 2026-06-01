from django.contrib import admin
from .models import Task, TaskCategory, TaskReminder

# Register your models here.

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'category', 'date', 'time', 'priority', 'status', 'created_at')
    list_filter = ('status', 'priority', 'category', 'date')
    search_fields = ('title', 'description', 'user__username')


@admin.register(TaskCategory)
class TaskCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'color', 'created_at')
    search_fields = ('name', 'user__username')


@admin.register(TaskReminder)
class TaskReminderAdmin(admin.ModelAdmin):
    list_display = ('task', 'remind_at', 'delivered', 'created_at')
    list_filter = ('delivered',)
