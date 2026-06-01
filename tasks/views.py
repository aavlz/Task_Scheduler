from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from datetime import datetime, timedelta
from dateutil import parser as date_parser
import re

from .models import Task, TaskCategory, TaskReminder
from .serializers import TaskCategorySerializer, TaskSerializer

# Create your views here.

class TaskViewSet(viewsets.ModelViewSet):
    """
    CRUD for tasks. Each user only sees their own tasks. 
    """
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Task.objects.select_related('category').filter(user=self.request.user)
        params = self.request.query_params
        today = timezone.localtime(timezone.now()).date()

        status_filter = params.get('status')
        priority_filter = params.get('priority')
        category_filter = params.get('category')
        search = params.get('search') or params.get('q')
        view = params.get('view')

        if status_filter:
            queryset = queryset.filter(status=status_filter.lower())
        if priority_filter:
            queryset = queryset.filter(priority=priority_filter.lower())
        if category_filter:
            queryset = queryset.filter(category__name__iexact=category_filter)
        if search:
            queryset = queryset.filter(title__icontains=search)
        if view == 'today':
            queryset = queryset.filter(date=today)
        elif view == 'upcoming':
            queryset = queryset.filter(date__gt=today)
        elif view == 'overdue':
            queryset = queryset.filter(status='pending', date__lt=today)
        elif view == 'completed':
            queryset = queryset.filter(status='completed')
        elif view == 'high':
            queryset = queryset.filter(priority='high', status='pending')

        return queryset

    def perform_create(self, serializer):
        task = serializer.save(user=self.request.user)
        self._sync_task_reminder(task)

    def perform_update(self, serializer):
        task = serializer.save()
        self._sync_task_reminder(task)

    def _sync_task_reminder(self, task):
        if not task.time:
            task.reminders.all().delete()
            return
        scheduled = datetime.combine(task.date, task.time)
        if timezone.is_naive(scheduled):
            scheduled = timezone.make_aware(scheduled, timezone.get_current_timezone())
        remind_at = scheduled - timedelta(minutes=task.reminder_minutes_before)
        TaskReminder.objects.update_or_create(
            task=task,
            defaults={'remind_at': remind_at, 'delivered': False},
        )


    # GET /api/tasks/summary/
    @action(detail=False, methods=['get'])
    def summary(self, request):
        tasks = self.get_queryset()
        today = timezone.localtime(timezone.now()).date()

        pending = tasks.filter(status='pending').count()
        completed = tasks.filter(status='completed').count()
        priority = tasks.filter(priority='high', status='pending').count()
        overdue = tasks.filter(status='pending', date__lt=today).count()

        return Response({
            'pending': pending,
            'completed': completed,
            'priority': priority,
            'overdue': overdue
        })
    
    # GET /api/tasks/today/
    @action(detail=False, methods=['get'])
    def today(self, request):
        today = timezone.localtime(timezone.now()).date()
        tasks = self.get_queryset().filter(date=today)
        serializer = self.get_serializer(tasks, many=True)
        return Response(serializer.data)
    
    # GET /api/tasks/upcoming/
    @action(detail=False, methods=['get'])
    def upcoming(self, request):
        today = timezone.localtime(timezone.now()).date()
        tasks = self.get_queryset().filter(date__gt=today)
        serializer = self.get_serializer(tasks, many=True)
        return Response(serializer.data)
    
    # POST /api/tasks/from-voice/
    @action(detail=False, methods=['post'], url_path='from-voice')
    def from_voice(self, request):
        """
        Parse a natural language voice command into a task.
        Example: "Add math quiz tomorrow at 3 PM priority high"
        """

        transcript = request.data.get('transcript', '').strip()
        if not transcript:
            return Response(
                {'error': 'No transcript provided.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            from voice_parser.services import VoiceCommandService

            result = VoiceCommandService(request.user).execute(transcript)
            if result.get('task'):
                return Response(result['task'], status=status.HTTP_201_CREATED)
            return Response(result, status=status.HTTP_200_OK)
        except Exception:
            parsed = self._parse_voice_command(transcript)

            serializer = self.get_serializer(data=parsed)
            serializer.is_valid(raise_exception=True)
            serializer.save(user=request.user)

            return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    def _parse_voice_command(self, transcript):
        """
        Simple NLP parser for voice commands.
        Extracts: title, date, time, priority.
        """

        text = transcript.lower().strip()
        now = timezone.localtime(timezone.now())

        priority = 'medium'
        for p in ['high', 'low', 'medium']:
            if f'priority {p}' in text or f'{p} priority' in text:
                priority = p
                text = re.sub(rf'(priority\s+{p}|{p}\s+priority)', '', text).strip()
                break

        time_str = '09:00'
        time_pattern = [
            r'\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b',
            r'\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b',
            r'\bat\s+(\d{1,2})(?::(\d{2}))?\b',
            r'\b(\d{1,2}):(\d{2})\b',
        ]
        for pattern in time_pattern:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                groups = match.groups()
                hour = int(groups[0])
                minute = int(groups[1]) if groups[1] and groups[1].isdigit() else 0
                ampm = groups[2].lower() if len(groups) > 2 and groups[2] else None
                if ampm:
                    if ampm == 'pm' and hour != 12:
                        hour += 12
                    elif ampm == 'am' and hour == 12:
                        hour = 0
                time_str = f'{hour:02d}:{minute:02d}'
                text = text[:match.start()] + text[match.end():]
                break
        
        task_date = now.date()
        if 'tomorrow' in text:
            task_date = now.date() + timedelta(days=1)
            text = text.replace('tomorrow', '').strip()
        elif 'today' in text:
            text = text.replace('today', '').strip()
        else:
            # Try to find a date like "May 18", "June 5", etc.
            date_match = re.search(
                r'(?:on\s+)?(\w+\s+\d{1,2}(?:,?\s*\d{4})?)', text
            )
            if date_match:
                try:
                    parsed_date = date_parser.parse(date_match.group(1), fuzzy=True)
                    task_date = parsed_date.date()
                    if task_date.year < now.year:
                        task_date = task_date.replace(year=now.year)
                    text = text[:date_match.start()] + text[date_match.end():]
                except (ValueError, OverflowError):
                    pass
        
        # Remove filter words and any remaining time/date helper tokens
        title = re.sub(r'\b(add|create|schedule|set|remind|me|to|a|an|the|at|on|today|tomorrow|am|pm)\b', '', text)
        title = re.sub(r'\s+', ' ', title).strip()
        title = title.capitalize() if title else 'Untitled Task'

        return {
            'title': title,
            'date': task_date.isoformat(),
            'time': time_str,
            'priority': priority,
            'status': 'pending',
        }


class TaskCategoryViewSet(viewsets.ModelViewSet):
    serializer_class = TaskCategorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        for name in TaskCategory.ALLOWED_NAMES:
            TaskCategory.objects.get_or_create(
                user=self.request.user,
                name=name,
                defaults={'color': TaskCategory.DEFAULT_COLORS.get(name, '#338A85')},
            )
        return TaskCategory.objects.filter(user=self.request.user, name__in=TaskCategory.ALLOWED_NAMES)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
