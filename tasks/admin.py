from django.contrib import admin
from .models import Task

# Register your models here.

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'date', 'time', 'priority', 'status', 'created_at')
    list_filter = ('status', 'priority', 'date')
    search_fields = ('title', 'description', 'user__username')