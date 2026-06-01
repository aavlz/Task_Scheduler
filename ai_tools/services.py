import json
import re

from django.conf import settings
from django.utils import timezone
import datetime

from tasks.models import Task

from .models import AIInsight


class AIService:
    def __init__(self, user):
        self.user = user

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
                    'filter_tasks, search_tasks, export_tasks, task_summary, how_to, logout. '
                    'Allowed priorities: low, medium, high. Allowed categories: School, Work, Personal, Others. '
                    'For dates, return date as YYYY-MM-DD when a task date is implied. '
                    'For times, return time as HH:MM in 24-hour format when implied. '
                    'For create_task, title must contain only the task name. Remove action words, dates, times, '
                    'priority words, category words, filler words like by/at/on/sa/ng, and punctuation artifacts. '
                    'Examples: "add grocery by 8 a.m." => title "grocery", time "08:00"; '
                    '"magdagdag ng quiz bukas alas tres ng hapon" => title "quiz", date tomorrow, time "15:00". '
                    'For update/delete/complete/search, query should be the task name or search phrase only. '
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

        if any(word in text for word in ['logout', 'log out', 'sign out']):
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
        if any(word in text for word in ['update', 'change', 'move', 'reschedule', 'edit', 'palitan', 'ilipat', 'baguhin']):
            return {'intent': 'update_task', 'query': self._after_marker(text, ['update', 'change', 'move', 'reschedule', 'edit', 'palitan', 'ilipat', 'baguhin']), 'confidence': 0.82, 'used_external_ai': False}
        if any(word in text for word in ['search', 'find', 'hanapin', 'maghanap']):
            return {'intent': 'search_tasks', 'query': self._after_marker(text, ['search', 'find', 'hanapin', 'maghanap']), 'confidence': 0.84, 'used_external_ai': False}
        if (
            any(phrase in text for phrase in ['show my tasks', 'list tasks', 'show tasks', 'ipakita'])
            or (('show' in text or 'list' in text) and ('task' in text or 'tasks' in text))
        ):
            return {'intent': 'filter_tasks', 'target': self._filter_target(text), 'confidence': 0.8, 'used_external_ai': False}
        if any(word in text for word in ['add', 'create', 'schedule', 'remind', 'gawa', 'gumawa', 'dagdag', 'idagdag', 'magdagdag', 'paalala']):
            return {'intent': 'create_task', 'confidence': 0.78, 'used_external_ai': False}
        return {'intent': 'create_task', 'confidence': 0.55, 'used_external_ai': False}

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
