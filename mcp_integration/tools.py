from collections import defaultdict
import json
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from tasks.models import Task


AVAILABLE_TOOLS = [
    {
        'slug': 'task-recommender',
        'name': 'Task Recommender',
        'description': 'Suggests the next tasks to work on based on urgency and priority.',
    },
    {
        'slug': 'smart-scheduler',
        'name': 'Smart Scheduler',
        'description': 'Proposes a practical schedule for pending tasks.',
    },
    {
        'slug': 'priority-optimizer',
        'name': 'Priority Optimizer',
        'description': 'Recommends priority changes based on dates and current status.',
    },
]


class MCPToolRunner:
    def __init__(self, user):
        self.user = user

    def list_tools(self):
        return AVAILABLE_TOOLS

    def execute(self, slug, payload=None):
        payload = payload or {}
        handlers = {
            'task-recommender': self._task_recommender,
            'smart-scheduler': self._smart_scheduler,
            'priority-optimizer': self._priority_optimizer,
        }
        if slug not in handlers:
            return {'success': False, 'error': 'Unknown tool.'}
        return {'success': True, 'tool': slug, 'result': handlers[slug](payload)}

    def _task_recommender(self, payload):
        tasks = Task.objects.filter(user=self.user, status='pending').order_by('date', 'time')
        ai_result = self._ai_tool_result(
            'Recommend the next tasks to work on. Return JSON with key recommended_tasks, each item having id, title, reason.',
            tasks[:25],
        )
        if ai_result:
            return ai_result
        weighted = sorted(tasks, key=lambda task: (self._priority_weight(task), task.date, task.time))
        return {
            'used_external_ai': False,
            'recommended_tasks': [
                {
                    'id': task.id,
                    'title': task.title,
                    'date': task.date.isoformat(),
                    'time': task.time.isoformat(timespec='minutes') if task.time else None,
                    'priority': task.priority,
                    'reason': self._recommendation_reason(task),
                }
                for task in weighted[:5]
            ]
        }

    def _smart_scheduler(self, payload):
        start = timezone.localdate()
        pending = Task.objects.filter(user=self.user, status='pending').order_by('date', 'time')
        ai_result = self._ai_tool_result(
            'Create a practical study/work schedule. Return JSON with key schedule grouped by YYYY-MM-DD.',
            pending[:25],
        )
        if ai_result:
            return ai_result
        schedule = defaultdict(list)
        for index, task in enumerate(pending[:15]):
            day = max(task.date, start + timedelta(days=index // 4))
            schedule[day.isoformat()].append({
                'id': task.id,
                'title': task.title,
                'suggested_time': task.time.isoformat(timespec='minutes') if task.time else None,
                'priority': task.priority,
            })
        return {'used_external_ai': False, 'schedule': dict(schedule)}

    def _priority_optimizer(self, payload):
        today = timezone.localdate()
        suggestions = []
        tasks = Task.objects.filter(user=self.user, status='pending').order_by('date', 'time')[:25]
        ai_result = self._ai_tool_result(
            'Suggest priority changes. Return JSON with key suggestions, each item having id, title, current_priority, suggested_priority, reason.',
            tasks,
        )
        if ai_result:
            return ai_result
        for task in tasks:
            suggested = task.priority
            reason = 'Priority looks appropriate.'
            if task.date < today and task.priority != 'high':
                suggested = 'high'
                reason = 'Overdue tasks should be raised to high priority.'
            elif task.date <= today + timedelta(days=1) and task.priority == 'low':
                suggested = 'medium'
                reason = 'Due soon, so low priority is risky.'
            suggestions.append({
                'id': task.id,
                'title': task.title,
                'current_priority': task.priority,
                'suggested_priority': suggested,
                'reason': reason,
            })
        return {'used_external_ai': False, 'suggestions': suggestions}

    def _ai_tool_result(self, instruction, tasks):
        if not (settings.GEMINI_API_KEY or settings.OPENAI_API_KEY):
            return None
        task_payload = [
            {
                'id': task.id,
                'title': task.title,
                'date': task.date.isoformat(),
                'time': task.time.isoformat(timespec='minutes') if task.time else None,
                'priority': task.priority,
                'status': task.status,
                'category': task.category.name if task.category else 'Others',
                'is_overdue': task.is_overdue,
            }
            for task in tasks
        ]
        prompt = (
            'You are the AI engine for V.A.S.T., a task scheduling app. '
            'Use the task data to produce concise, actionable JSON only. '
            f'{instruction} Tasks: {json.dumps(task_payload)}'
        )
        return self._gemini_json(prompt) or self._openai_json(prompt)

    def _gemini_json(self, prompt):
        if not settings.GEMINI_API_KEY:
            return None
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type='application/json', temperature=0.2),
            )
            data = json.loads(response.text.strip())
            if isinstance(data, dict):
                data['used_external_ai'] = True
                data['provider'] = 'gemini'
                return data
        except Exception:
            return None
        return None

    def _openai_json(self, prompt):
        if not settings.OPENAI_API_KEY:
            return None
        try:
            from openai import OpenAI

            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            response = client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                response_format={'type': 'json_object'},
                messages=[
                    {'role': 'system', 'content': 'Return JSON only.'},
                    {'role': 'user', 'content': prompt},
                ],
            )
            data = json.loads(response.choices[0].message.content)
            if isinstance(data, dict):
                data['used_external_ai'] = True
                data['provider'] = 'openai'
                return data
        except Exception:
            return None
        return None

    def _priority_weight(self, task):
        return {'high': 0, 'medium': 1, 'low': 2}.get(task.priority, 1)

    def _recommendation_reason(self, task):
        if task.date < timezone.localdate():
            return 'Overdue and still pending.'
        if task.priority == 'high':
            return 'High priority and pending.'
        return 'Next chronological pending task.'
