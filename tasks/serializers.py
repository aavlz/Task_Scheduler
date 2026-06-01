from rest_framework import serializers
from .models import Task

class TaskSerializer(serializers.ModelSerializer):
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = Task
        fields = ['id', 'title', 'date', 'time', 'priority', 'status', 'is_overdue', 'created_at']
        read_only_fields = ['id', 'created_at', 'is_overdue']