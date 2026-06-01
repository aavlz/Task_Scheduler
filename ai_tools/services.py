import json
import re
from collections import defaultdict

from django.conf import settings
from django.utils import timezone
import datetime

from tasks.models import Task

from .models import AIInsight


class AIService:
    def __init__(self, user):
        self.user = user

    AI_COMMANDS = {
        'smart_schedule': {
            'title': 'Smart Schedule',
            'summary': 'Plan the best order for today and upcoming tasks.',
        },
        'auto_prioritize': {
            'title': 'Auto Prioritize',
            'summary': 'Suggest which tasks should be high, medium, or low priority.',
        },
        'duplicate_cleanup': {
            'title': 'Duplicate Cleanup',
            'summary': 'Find likely duplicate tasks before you delete anything.',
        },
        'task_breakdown': {
            'title': 'Task Breakdown',
            'summary': 'Break a large task into smaller steps.',
        },
        'natural_reschedule': {
            'title': 'Natural Reschedule',
            'summary': 'Suggest safe rescheduling moves for matching tasks.',
        },
        'daily_briefing': {
            'title': 'Daily Briefing',
            'summary': 'Summarize what needs attention today.',
        },
        'smart_search': {
            'title': 'Smart Search',
            'summary': 'Find tasks by meaning or related words.',
        },
        'motivation': {
            'title': 'Motivation Coach',
            'summary': 'Give a short task-aware encouragement.',
        },
        'workload_analysis': {
            'title': 'Workload Analysis',
            'summary': 'Explain whether the workload is balanced or overloaded.',
        },
        'reminder_suggestions': {
            'title': 'Reminder Suggestions',
            'summary': 'Suggest better reminder timing for tasks.',
        },
    }

    def summarize_tasks(self):
        tasks = list(Task.objects.filter(user=self.user).select_related('category'))
        today = timezone.localdate()
        pending = [task for task in tasks if task.status == 'pending']
        completed = [task for task in tasks if task.status == 'completed']
        overdue = [task for task in pending if task.date < today]
        high = [task for task in pending if task.priority == 'high']

        fallback = {
            'summary': (
                f'You have {len(pending)} pending task(s), {len(completed)} completed task(s), '
                f'{len(high)} high priority task(s), and {len(overdue)} overdue task(s).'
            ),
            'recommendations': self._rule_based_recommendations(pending, overdue, high),
            'priority_suggestions': self._priority_suggestions(pending),
            'used_external_ai': False,
        }

        ai_result = self._gemini_summary(tasks) or self._external_summary(tasks)
        result = ai_result or fallback
        AIInsight.objects.create(
            user=self.user,
            insight_type='summary',
            prompt='Summarize tasks and recommend next actions.',
            response=result,
            used_external_ai=result.get('used_external_ai', False),
        )
        return result

    def run_ai_command(self, intent, transcript='', query=''):
        tasks = list(Task.objects.filter(user=self.user).select_related('category'))
        intent = intent if intent in self.AI_COMMANDS else 'daily_briefing'
        fallback = self._rule_based_ai_command(intent, tasks, transcript=transcript, query=query)
        ai_result = self._gemini_ai_command(intent, tasks, transcript=transcript, query=query)
        result = ai_result or fallback
        result.setdefault('command', intent)
        result.setdefault('action', 'ai_command')
        result.setdefault('used_external_ai', False)
        AIInsight.objects.create(
            user=self.user,
            insight_type='recommendation',
            prompt=transcript or intent,
            response=result,
            used_external_ai=result.get('used_external_ai', False),
        )
        return result

    def ai_commands_guide(self):
        return {
            'summary': 'AI Commands can plan, prioritize, search, explain, and suggest changes without making bulk edits automatically.',
            'recommendations': [
                'Plan my day / Ayusin mo schedule ko today.',
                'Prioritize my tasks / Ano ang unahin ko?',
                'Find duplicate tasks / Clean up my tasks.',
                'Break down final project into steps.',
                'Move overdue tasks to tomorrow morning.',
                'Give me my daily briefing / What should I do today?',
                'Find tasks related to school deadlines.',
                'Motivate me / Help me start.',
                'Analyze my workload / May sobrang dami ba akong task?',
                'Suggest reminders for my tasks.',
            ],
            'used_external_ai': False,
        }

    def classify_voice_intent(self, transcript, context_phrases=None):
        fallback = self._rule_based_voice_intent(transcript)
        ai_result = None
        if self._should_use_external_voice_ai(fallback):
            ai_result = self._gemini_voice_intent(transcript, context_phrases=context_phrases) or self._external_voice_intent(transcript)
        result = ai_result or fallback
        AIInsight.objects.create(
            user=self.user,
            insight_type='voice_intent',
            prompt=transcript,
            response=result,
            used_external_ai=result.get('used_external_ai', False),
        )
        return result

    def _should_use_external_voice_ai(self, fallback):
        if not settings.GEMINI_API_KEY and not settings.OPENAI_API_KEY:
            return False
        # Keep deterministic handling for high-confidence app/navigation commands.
        return float(fallback.get('confidence') or 0) < 0.85

    def _rule_based_recommendations(self, pending, overdue, high):
        recommendations = []
        if overdue:
            recommendations.append('Start with overdue tasks before creating new work.')
        if high:
            recommendations.append('Focus on high priority tasks with the nearest due date.')
        if not recommendations and pending:
            recommendations.append('Work through today and upcoming tasks in chronological order.')
        if not pending:
            recommendations.append('No pending tasks. Review completed work or add the next priority.')
        return recommendations

    def _priority_suggestions(self, pending):
        suggestions = []
        for task in sorted(pending, key=lambda item: (item.date, item.time))[:5]:
            suggested = task.priority
            if task.date < timezone.localdate() and task.priority != 'high':
                suggested = 'high'
            suggestions.append({
                'task_id': task.id,
                'title': task.title,
                'current_priority': task.priority,
                'suggested_priority': suggested,
            })
        return suggestions

    def _task_payload(self, tasks):
        return [
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
            for task in tasks[:40]
        ]

    def _rule_based_ai_command(self, intent, tasks, transcript='', query=''):
        today = timezone.localdate()
        pending = [task for task in tasks if task.status == 'pending']
        overdue = [task for task in pending if task.date < today]
        today_tasks = [task for task in pending if task.date == today]
        high = [task for task in pending if task.priority == 'high']

        if intent == 'smart_schedule':
            ordered = sorted(pending, key=lambda item: (item.date, item.time or datetime.time(23, 59), {'high': 0, 'medium': 1, 'low': 2}.get(item.priority, 1)))[:6]
            return {
                'summary': 'Here is a practical order for your next tasks.',
                'recommendations': [f'{idx + 1}. {task.title} ({task.date.isoformat()} {task.time.strftime("%H:%M") if task.time else "no set time"}, {task.priority})' for idx, task in enumerate(ordered)] or ['No pending tasks to schedule.'],
                'tasks': self._task_payload(ordered),
            }

        if intent == 'auto_prioritize':
            suggestions = self._priority_suggestions(pending)
            return {
                'summary': 'I checked urgency, due dates, and overdue tasks for priority suggestions.',
                'recommendations': [
                    f'{item["title"]}: {item["current_priority"]} -> {item["suggested_priority"]}'
                    for item in suggestions
                ] or ['No pending tasks need reprioritizing.'],
                'priority_suggestions': suggestions,
            }

        if intent == 'duplicate_cleanup':
            groups = defaultdict(list)
            for task in pending:
                key = re.sub(r'[^a-z0-9]+', ' ', task.title.lower()).strip()
                groups[(key, task.date, task.time)].append(task)
            duplicates = [items for items in groups.values() if len(items) > 1]
            return {
                'summary': f'I found {len(duplicates)} possible duplicate group(s).',
                'recommendations': [
                    'Possible duplicate: ' + ', '.join(task.title for task in group)
                    for group in duplicates[:5]
                ] or ['No obvious duplicates found.'],
                'duplicate_groups': [[task.id for task in group] for group in duplicates[:5]],
            }

        if intent == 'task_breakdown':
            target = self._find_task_by_text(tasks, query or transcript)
            title = target.title if target else (query or 'your task').strip()
            return {
                'summary': f'Break "{title}" into small steps before scheduling it.',
                'recommendations': [
                    f'Clarify the expected output for {title}.',
                    'Gather needed materials or references.',
                    'Do the first 25-minute work session.',
                    'Review the result and list what remains.',
                    'Set a final check or submission reminder.',
                ],
            }

        if intent == 'natural_reschedule':
            target_tasks = overdue or pending[:3]
            tomorrow = today + datetime.timedelta(days=1)
            return {
                'summary': f'I can suggest moving {len(target_tasks)} task(s), but I will not bulk-edit without confirmation.',
                'recommendations': [
                    f'Move "{task.title}" to {tomorrow.isoformat()} at 09:00.'
                    for task in target_tasks[:5]
                ] or ['No pending tasks need rescheduling.'],
                'requires_confirmation': True,
            }

        if intent == 'daily_briefing':
            return {
                'summary': f'Today you have {len(today_tasks)} task(s), {len(overdue)} overdue, and {len(high)} high priority pending.',
                'recommendations': self._rule_based_recommendations(pending, overdue, high),
                'tasks': self._task_payload(sorted(today_tasks or pending, key=lambda item: (item.date, item.time or datetime.time(23, 59)))[:5]),
            }

        if intent == 'smart_search':
            matches = self._smart_search_tasks(tasks, query or transcript)
            return {
                'summary': f'I found {len(matches)} task(s) that look related.',
                'recommendations': [f'{task.title} ({task.category.name if task.category else "Others"}, {task.date.isoformat()})' for task in matches[:8]] or ['No related tasks found.'],
                'tasks': self._task_payload(matches[:8]),
            }

        if intent == 'motivation':
            next_task = sorted(pending, key=lambda item: (item.date, item.time or datetime.time(23, 59)))[0] if pending else None
            return {
                'summary': f'Start small: open "{next_task.title}" and work for just 10 minutes.' if next_task else 'You have no pending tasks. Nice work. Pick one useful thing to prepare next.',
                'recommendations': ['Lower the starting friction.', 'Focus on the next visible action.', 'Mark one small win before switching tasks.'],
            }

        if intent == 'workload_analysis':
            by_date = defaultdict(int)
            for task in pending:
                by_date[task.date] += 1
            busiest = sorted(by_date.items(), key=lambda item: item[1], reverse=True)[:3]
            return {
                'summary': f'You have {len(pending)} pending task(s). The busiest day has {busiest[0][1] if busiest else 0} task(s).',
                'recommendations': [f'{day.isoformat()}: {count} pending task(s).' for day, count in busiest] or ['No workload pressure detected.'],
            }

        if intent == 'reminder_suggestions':
            ordered = sorted(pending, key=lambda item: (item.date, item.time or datetime.time(23, 59)))[:8]
            return {
                'summary': 'Here are reminder timing suggestions based on urgency and category.',
                'recommendations': [
                    f'{task.title}: {"1 day before" if task.priority == "high" else "2 hours before" if task.category and task.category.name == "School" else "10 minutes before"}.'
                    for task in ordered
                ] or ['No pending tasks need reminders.'],
            }

        return self.summarize_tasks()

    def _find_task_by_text(self, tasks, text):
        cleaned = re.sub(r'\b(break|down|split|steps|task|into|gawan|mo|ng|yung)\b', '', (text or '').lower()).strip()
        if not cleaned:
            return None
        return max(tasks, key=lambda task: self._text_score(cleaned, task.title), default=None)

    def _smart_search_tasks(self, tasks, text):
        query = re.sub(r'\b(find|search|show|tasks|related|about|tungkol|hanapin|mo|yung)\b', '', (text or '').lower()).strip()
        scored = [(self._text_score(query, f'{task.title} {task.category.name if task.category else ""} {task.priority}'), task) for task in tasks]
        return [task for score, task in sorted(scored, key=lambda item: item[0], reverse=True) if score > 0][:10]

    def _text_score(self, query, text):
        query_tokens = set(re.findall(r'[a-z0-9]+', query.lower()))
        text_tokens = set(re.findall(r'[a-z0-9]+', text.lower()))
        if not query_tokens:
            return 0
        return len(query_tokens & text_tokens)

    def _external_summary(self, tasks):
        if not settings.OPENAI_API_KEY:
            return None
        try:
            from openai import OpenAI

            task_payload = [
                {
                    'title': task.title,
                    'date': task.date.isoformat(),
                    'time': task.time.isoformat(timespec='minutes'),
                    'priority': task.priority,
                    'status': task.status,
                    'category': task.category.name if task.category else '',
                }
                for task in tasks[:30]
            ]
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            response = client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                response_format={'type': 'json_object'},
                messages=[
                    {
                        'role': 'system',
                        'content': (
                            'Return JSON with keys summary, recommendations, and priority_suggestions. '
                            'Keep recommendations short and practical.'
                        ),
                    },
                    {'role': 'user', 'content': json.dumps(task_payload)},
                ],
            )
            data = json.loads(response.choices[0].message.content)
            data['used_external_ai'] = True
            return data
        except Exception:
            return None

    def _gemini_summary(self, tasks):
        if not settings.GEMINI_API_KEY:
            return None
        try:
            from google import genai
            from google.genai import types

            task_payload = [
                {
                    'title': task.title,
                    'date': task.date.isoformat(),
                    'time': task.time.isoformat(timespec='minutes') if task.time else None,
                    'priority': task.priority,
                    'status': task.status,
                    'category': task.category.name if task.category else 'Others',
                }
                for task in tasks[:30]
            ]
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=(
                    'Summarize these V.A.S.T. tasks for a student user. Return concise JSON only with '
                    'summary as a string, recommendations as a list of strings, and priority_suggestions '
                    'as a list of objects. Tasks: '
                    f'{json.dumps(task_payload)}'
                ),
                config=types.GenerateContentConfig(
                    response_mime_type='application/json',
                    temperature=0.2,
                ),
            )
            data = self._parse_json_text(response.text)
            if not isinstance(data, dict) or 'summary' not in data:
                return None
            data.setdefault('recommendations', [])
            data.setdefault('priority_suggestions', [])
            data['used_external_ai'] = True
            data['provider'] = 'gemini'
            return data
        except Exception:
            return None

    def _gemini_ai_command(self, intent, tasks, transcript='', query=''):
        if not settings.GEMINI_API_KEY:
            return None
        try:
            from google import genai
            from google.genai import types

            command = self.AI_COMMANDS.get(intent, self.AI_COMMANDS['daily_briefing'])
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=(
                    'You are the V.A.S.T. task assistant. Return concise JSON only with keys: '
                    'summary string, recommendations list of strings, priority_suggestions list, '
                    'requires_confirmation boolean, and tasks list of task IDs when relevant. '
                    'Do not claim that tasks were changed. For reschedule, cleanup, reminders, and priority changes, '
                    'suggest actions and require confirmation. '
                    f'Command: {intent} - {command["summary"]}. '
                    f'User phrase: {transcript}. Query: {query}. '
                    f'Tasks: {json.dumps(self._task_payload(tasks))}'
                ),
                config=types.GenerateContentConfig(
                    response_mime_type='application/json',
                    temperature=0.25,
                ),
            )
            data = self._parse_json_text(response.text)
            if not isinstance(data, dict) or not isinstance(data.get('summary'), str):
                return None
            data.setdefault('recommendations', [])
            data.setdefault('priority_suggestions', [])
            data.setdefault('requires_confirmation', intent in ['natural_reschedule', 'duplicate_cleanup', 'reminder_suggestions', 'auto_prioritize'])
            data['used_external_ai'] = True
            data['provider'] = 'gemini'
            data['command'] = intent
            data['action'] = 'ai_command'
            return data
        except Exception:
            return None

    def _gemini_voice_intent(self, transcript, context_phrases=None):
        if not settings.GEMINI_API_KEY:
            return None
        try:
            from google import genai
            from google.genai import types

            today = timezone.localdate().isoformat()
            phrase_context = ', '.join((context_phrases or [])[:40])
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=(
                    'You classify voice commands for V.A.S.T., a task scheduling app. '
                    f'Today is {today} in Asia/Manila. Return JSON only. '
                    'Allowed intents: navigate, create_task, update_task, complete_task, delete_task, '
                    'filter_tasks, search_tasks, export_tasks, task_summary, how_to, logout, '
                    'smart_schedule, auto_prioritize, duplicate_cleanup, task_breakdown, natural_reschedule, '
                    'daily_briefing, smart_search, motivation, workload_analysis, reminder_suggestions. '
                    'Allowed priorities: low, medium, high. Allowed categories: School, Work, Personal, Others. '
                    'For dates, return date as YYYY-MM-DD when a task date is implied. '
                    'For times, return time as HH:MM in 24-hour format when implied. '
                    'For create_task, title must contain only the task name. Remove action words, dates, times, '
                    'priority words, category words, filler words like by/at/on/sa/ng, and punctuation artifacts. '
                    'Examples: "add grocery by 8 a.m." => title "grocery", time "08:00"; '
                    '"magdagdag ng quiz bukas alas tres ng hapon" => title "quiz", date tomorrow, time "15:00". '
                    'For update/delete/complete/search, query should be the task name or search phrase only. '
                    'Use smart_schedule for plan my day/schedule my tasks. Use auto_prioritize for prioritize/what first. '
                    'Use duplicate_cleanup for duplicate/cleanup repeated tasks. Use task_breakdown for split/break into steps. '
                    'Use natural_reschedule for move all overdue/remaining tasks. Use daily_briefing for what should I do today. '
                    'Use smart_search for related/about/meaning-based task searches. Use motivation for overwhelmed/help me start. '
                    'Use workload_analysis for overloaded/workload/busy questions. Use reminder_suggestions for better reminders. '
                    'For filter target, use today, tomorrow, completed, overdue, high, School, Work, Personal, Others, or all. '
                    'Use known vocabulary to correct likely transcription mistakes before deciding fields. '
                    f'Known vocabulary and existing task names: {phrase_context}. '
                    'Return keys: intent, confidence, query, target, title, date, time, priority, category. '
                    f'Transcript: {transcript}'
                ),
                config=types.GenerateContentConfig(
                    response_mime_type='application/json',
                    temperature=0.1,
                ),
            )
            data = self._parse_json_text(response.text)
            return self._validate_voice_ai_result(data)
        except Exception:
            return None

    def _parse_json_text(self, text):
        if not text:
            return None
        cleaned = text.strip()
        if cleaned.startswith('```'):
            cleaned = re.sub(r'^```(?:json)?\s*|\s*```$', '', cleaned, flags=re.IGNORECASE | re.DOTALL).strip()
        return json.loads(cleaned)

    def _validate_voice_ai_result(self, data):
        if not isinstance(data, dict):
            return None
        allowed_intents = {
            'navigate',
            'create_task',
            'update_task',
            'complete_task',
            'delete_task',
            'filter_tasks',
            'search_tasks',
            'export_tasks',
            'task_summary',
            'how_to',
            'logout',
            'smart_schedule',
            'auto_prioritize',
            'duplicate_cleanup',
            'task_breakdown',
            'natural_reschedule',
            'daily_briefing',
            'smart_search',
            'motivation',
            'workload_analysis',
            'reminder_suggestions',
        }
        intent = data.get('intent')
        if intent not in allowed_intents:
            return None
        try:
            confidence = max(0.0, min(1.0, float(data.get('confidence') or 0.65)))
        except (TypeError, ValueError):
            confidence = 0.65

        normalized = {
            'intent': intent,
            'confidence': confidence,
            'used_external_ai': True,
            'provider': 'gemini',
        }
        for key in ['query', 'target', 'title', 'date', 'time']:
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                normalized[key] = value.strip()
        priority = data.get('priority')
        if priority in ['low', 'medium', 'high']:
            normalized['priority'] = priority
        category = data.get('category')
        if category in ['School', 'Work', 'Personal', 'Others']:
            normalized['category'] = category
            normalized['target'] = normalized.get('target') or category
        return normalized

    def _external_voice_intent(self, transcript):
        if not settings.OPENAI_API_KEY:
            return None
        try:
            from openai import OpenAI

            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            response = client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                response_format={'type': 'json_object'},
                messages=[
                    {
                        'role': 'system',
                        'content': (
                            'Classify a task app voice command. Return JSON with intent, confidence, '
                            'action, title, date_phrase, time_phrase, priority, category, query, and target.'
                        ),
                    },
                    {'role': 'user', 'content': transcript},
                ],
            )
            data = json.loads(response.choices[0].message.content)
            data['used_external_ai'] = True
            return data
        except Exception:
            return None

    def transcribe_audio(self, audio_file):
        """Transcribe uploaded audio using OpenAI Whisper (if configured).
        Expects a Django UploadedFile-like object.
        Returns the transcript string or None on failure/unsupported.
        """
        if not settings.OPENAI_API_KEY:
            return None
        try:
            from openai import OpenAI

            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            # audio_file may be InMemoryUploadedFile or TemporaryUploadedFile; pass the file-like object
            file_obj = getattr(audio_file, 'file', audio_file)
            resp = client.audio.transcriptions.create(file=file_obj, model='whisper-1')
            # The response format varies by SDK; attempt to extract text
            text = None
            if hasattr(resp, 'text'):
                text = resp.text
            else:
                # try dict-like
                text = resp.get('text') if isinstance(resp, dict) else None
            return text
        except Exception:
            return None

    def _rule_based_voice_intent(self, transcript):
        text = transcript.lower().strip()
        ai_command = self._rule_based_ai_command_intent(text)
        if ai_command:
            return ai_command

        navigation = {
            'dashboard': ('navigate', 'dashboard'),
            'calendar': ('navigate', 'calendar'),
            'settings': ('navigate', 'settings'),
            'profile': ('navigate', 'settings'),
            'categories': ('filter_tasks', 'categories'),
        }
        for keyword, target in navigation.items():
            if keyword in text and any(word in text for word in ['go', 'show', 'open', 'punta', 'buksan']):
                return {'intent': target[0], 'target': target[1], 'confidence': 0.82, 'used_external_ai': False}

        if any(word in text for word in ['logout', 'log out', 'sign out', 'signout']):
            return {'intent': 'logout', 'confidence': 0.9, 'used_external_ai': False}
        if any(phrase in text for phrase in ['how to', 'how do i', 'help', 'guide', 'paano']):
            return {'intent': 'how_to', 'confidence': 0.88, 'used_external_ai': False}
        if any(word in text for word in ['summary', 'summarize', 'buod']):
            return {'intent': 'task_summary', 'confidence': 0.86, 'used_external_ai': False}
        if 'export' in text:
            return {'intent': 'export_tasks', 'confidence': 0.8, 'used_external_ai': False}
        if any(word in text for word in ['complete', 'done', 'finish', 'tapusin', 'kumpleto', 'markahan']):
            return {'intent': 'complete_task', 'query': self._after_marker(text, ['complete', 'done', 'finish', 'tapusin', 'kumpleto', 'markahan']), 'confidence': 0.82, 'used_external_ai': False}
        if any(word in text for word in ['delete', 'remove', 'burahin', 'tanggalin', 'alisin']):
            return {'intent': 'delete_task', 'query': self._after_marker(text, ['delete', 'remove', 'burahin', 'tanggalin', 'alisin']), 'confidence': 0.82, 'used_external_ai': False}
        if any(word in text for word in ['update', 'change', 'move', 'reschedule', 'edit', 'palitan', 'ilipat', 'baguhin', 'adjust', 'modify']):
            return {'intent': 'update_task', 'query': self._after_marker(text, ['update', 'change', 'move', 'reschedule', 'edit', 'palitan', 'ilipat', 'baguhin', 'adjust', 'modify']), 'confidence': 0.82, 'used_external_ai': False}
        if any(word in text for word in ['search', 'find', 'hanapin', 'maghanap']):
            return {'intent': 'search_tasks', 'query': self._after_marker(text, ['search', 'find', 'hanapin', 'maghanap']), 'confidence': 0.84, 'used_external_ai': False}
        if (
            any(phrase in text for phrase in ['show my tasks', 'list tasks', 'show tasks', 'view tasks', 'display tasks', 'ipakita'])
            or (('show' in text or 'list' in text or 'view' in text) and ('task' in text or 'tasks' in text))
        ):
            return {'intent': 'filter_tasks', 'target': self._filter_target(text), 'confidence': 0.8, 'used_external_ai': False}
        if any(word in text for word in ['add', 'create', 'schedule', 'remind', 'make', 'set', 'new', 'gawa', 'gumawa', 'dagdag', 'idagdag', 'magdagdag', 'paalala', 'iskedyul']):
            return {'intent': 'create_task', 'confidence': 0.78, 'used_external_ai': False}
        return {'intent': 'create_task', 'confidence': 0.55, 'used_external_ai': False}

    def _rule_based_ai_command_intent(self, text):
        checks = [
            ('duplicate_cleanup', ['duplicate', 'duplicates', 'repeated', 'same task', 'clean up my tasks', 'cleanup', 'linisin']),
            ('smart_schedule', ['plan my day', 'plan today', 'schedule my day', 'schedule my tasks', 'best order', 'ayusin mo schedule', 'ayos schedule']),
            ('auto_prioritize', ['prioritize', 'priority suggestions', 'what should i do first', 'which task first', 'ano ang unahin', 'unahin ko']),
            ('task_breakdown', ['break down', 'split', 'steps for', 'make steps', 'subtasks', 'gawan mo ng steps', 'hatiin']),
            ('natural_reschedule', ['move all overdue', 'move overdue', 'reschedule all', 'move remaining', 'busy today', 'lipat lahat', 'ilipat overdue']),
            ('daily_briefing', ['daily briefing', 'briefing', 'what should i do today', 'what do i do today', 'gagawin ko ngayon', 'agenda today']),
            ('smart_search', ['related to', 'about', 'similar to', 'meaning of', 'tungkol sa', 'kaugnay']),
            ('motivation', ['motivate', 'motivation', 'help me start', 'overwhelmed', 'encourage', 'nahihirapan', 'nakaka overwhelm']),
            ('workload_analysis', ['workload', 'overloaded', 'too many tasks', 'busy week', 'analyze my workload', 'sobrang dami', 'tambak']),
            ('reminder_suggestions', ['suggest reminders', 'better reminders', 'set better reminders', 'reminder suggestions', 'paalala suggestions']),
        ]
        for intent, markers in checks:
            if any(marker in text for marker in markers):
                return {
                    'intent': intent,
                    'query': self._ai_query(text, markers),
                    'confidence': 0.86,
                    'used_external_ai': False,
                }
        return None

    def _ai_query(self, text, markers):
        query = text
        for marker in markers:
            query = query.replace(marker, ' ')
        return re.sub(r'\s+', ' ', query).strip(' :')

    def _filter_target(self, text):
        if 'tomorrow' in text or 'bukas' in text:
            return 'tomorrow'
        if 'today' in text or 'ngayon' in text:
            return 'today'
        if 'completed' in text or 'done' in text:
            return 'completed'
        if 'overdue' in text:
            return 'overdue'
        if 'high' in text or 'priority' in text:
            return 'high'
        category_match = text.split('category', 1)[0].rsplit(' ', 1)
        if 'category' in text and category_match:
            candidate = category_match[-1].strip()
            if candidate:
                return candidate
        if ' in ' in text:
            candidate = text.rsplit(' in ', 1)[-1].replace('category', '').strip()
            if candidate:
                return candidate
        return 'all'

    def _after_marker(self, text, markers):
        for marker in markers:
            if marker in text:
                return text.split(marker, 1)[1].replace('task', '').strip(' :')
        return text

    def prepare_morning_notification(self, date=None):
        """Prepare a notification payload 2 hours before the user's first task of the day.

        Returns a dict with keys: task_id, notify_at (ISO string or None), prompt (LLM prompt placeholder).
        """
        date = date or timezone.localdate()
        # Prefer pending tasks so we encourage upcoming work
        first_task = Task.objects.filter(user=self.user, date=date).exclude(status='completed').order_by('time', 'created_at').first()
        if not first_task:
            # No pending tasks; nothing to prepare
            return {'task_id': None, 'notify_at': None, 'prompt': None}

        if first_task.time:
            dt = datetime.datetime.combine(first_task.date, first_task.time)
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, timezone.get_current_timezone())
            notify_at = dt - datetime.timedelta(hours=2)
            notify_at_iso = notify_at.isoformat()
        else:
            # No explicit time; do not schedule time-based morning notification
            notify_at_iso = None

        prompt = (
            f"(LLM) Morning motivation for your upcoming task '{first_task.title}'. "
            f"Due: {first_task.date.isoformat()} {first_task.time.isoformat() if first_task.time else ''}. "
            "Return one short and unique motivational phrase tailored to this task."
        )
        return {'task_id': first_task.id, 'notify_at': notify_at_iso, 'prompt': prompt}

    def prepare_evening_notification(self, date=None):
        """Prepare an evening congratulatory prompt based on the user's last task of the day.

        Returns a dict with keys: task_id, notify_at (ISO), prompt (LLM prompt placeholder).
        """
        date = date or timezone.localdate()
        # find the last task of the day (prefer completed ones, fall back to latest target)
        last_task = Task.objects.filter(user=self.user, date=date).order_by('-time', '-created_at').first()
        if not last_task:
            return {'task_id': None, 'notify_at': None, 'prompt': None}

        # Schedule evening notification at 20:00 local time
        eve_time = datetime.time(hour=20)
        dt = datetime.datetime.combine(date, eve_time)
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        notify_at_iso = dt.isoformat()

        prompt = (
            f"(LLM) Evening summary congratulation for task '{last_task.title}'. "
            f"Status: {last_task.status}. Provide a short, personalized 'job well done' message referencing the task."
        )
        return {'task_id': last_task.id, 'notify_at': notify_at_iso, 'prompt': prompt}