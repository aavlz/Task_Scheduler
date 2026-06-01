from rest_framework import serializers
from .models import Task, TaskCategory


def normalize_category_name(value):
    if not value:
        return ''
    cleaned = value.strip().lower()
    aliases = {
        'school': 'School',
        'paaralan': 'School',
        'eskwela': 'School',
        'skwela': 'School',
        'klase': 'School',
        'class': 'School',
        'classes': 'School',
        'assignment': 'School',
        'trabaho': 'Work',
        'opisina': 'Work',
        'work': 'Work',
        'office': 'Work',
        'personal': 'Personal',
        'sarili': 'Personal',
        'pansarili': 'Personal',
        'bahay': 'Personal',
        'home': 'Personal',
        'others': 'Others',
        'other': 'Others',
        'iba': 'Others',
        'iba pa': 'Others',
        'misc': 'Others',
    }
    return aliases.get(cleaned, '')


class TaskSerializer(serializers.ModelSerializer):
    is_overdue = serializers.BooleanField(read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_label = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Task
        fields = [
            'id',
            'title',
            'description',
            'date',
            'time',
            'priority',
            'status',
            'reminder_minutes_before',
            'category',
            'category_name',
            'category_label',
            'is_overdue',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at', 'is_overdue']

    def validate_reminder_minutes_before(self, value):
        if value > 43200:
            raise serializers.ValidationError('Reminder can be at most 30 days before the task.')
        return value

    def validate_priority(self, value):
        normalized = value.lower()
        if normalized not in dict(Task.PRIORITY_CHOICES):
            raise serializers.ValidationError('Priority must be low, medium, or high.')
        return normalized

    def validate_status(self, value):
        normalized = value.lower()
        if normalized not in dict(Task.STATUS_CHOICES):
            raise serializers.ValidationError('Status must be pending or completed.')
        return normalized

    def validate_category(self, value):
        request = self.context.get('request')
        if request and value and value.user_id != request.user.id:
            raise serializers.ValidationError('Category does not belong to the current user.')
        return value

    def validate_category_label(self, value):
        if value and not normalize_category_name(value):
            allowed = ', '.join(TaskCategory.ALLOWED_NAMES)
            raise serializers.ValidationError(f'Category must be one of: {allowed}.')
        return value

    def _category_from_label(self, label):
        request = self.context.get('request')
        if not request:
            return None
        normalized = normalize_category_name(label) or 'Others'
        category, _ = TaskCategory.objects.get_or_create(
            user=request.user,
            name=normalized,
            defaults={'color': TaskCategory.DEFAULT_COLORS.get(normalized, '#338A85')},
        )
        return category

    def create(self, validated_data):
        label = validated_data.pop('category_label', None)
        if label is not None or not validated_data.get('category'):
            category = self._category_from_label(label or 'Others')
            validated_data['category'] = category
        return super().create(validated_data)

    def update(self, instance, validated_data):
        label = validated_data.pop('category_label', None)
        if label is not None:
            validated_data['category'] = self._category_from_label(label) if label else None
        return super().update(instance, validated_data)


class TaskCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskCategory
        fields = ['id', 'name', 'color', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_name(self, value):
        normalized = normalize_category_name(value)
        if not normalized:
            allowed = ', '.join(TaskCategory.ALLOWED_NAMES)
            raise serializers.ValidationError(f'Category must be one of: {allowed}.')
        return normalized

    def validate_color(self, value):
        name = self.initial_data.get('name') if hasattr(self, 'initial_data') else ''
        normalized = normalize_category_name(name)
        return TaskCategory.DEFAULT_COLORS.get(normalized, value)
