import json
import re
from difflib import SequenceMatcher
from datetime import date, time, timedelta

from dateutil import parser as date_parser
from django.contrib.auth import logout
from django.utils import timezone

from ai_tools.services import AIService
from tasks.models import Task
from tasks.serializers import TaskSerializer, normalize_category_name

from .models import VoiceAnalytics, VoiceCommand


KNOWN_VOICE_PHRASES = [
    'App Dev',
    'Application Development',
    'COMP 019',
    'VAST',
    'Final Project',
    'Capstone',
    'Database',
    'Django',
    'Railway',
    'Gemini',
    'SendGrid',
]

VOICE_CORRECTIONS = {
    'up dev': 'App Dev',
    'app dead': 'App Dev',
    'abd ev': 'App Dev',
    'ab dev': 'App Dev',
    'application develop meant': 'Application Development',
    'vast project': 'VAST Project',
    'fast project': 'VAST Project',
    'comp nineteen': 'COMP 019',
    'comp zero nineteen': 'COMP 019',
    'come zero nineteen': 'COMP 019',
    'real way': 'Railway',
    'send grid': 'SendGrid',
}

FILIPINO_WEEKDAYS = {
    'lunes': 'monday',
    'monday': 'monday',
    'martes': 'tuesday',
    'tuesday': 'tuesday',
    'miyerkules': 'wednesday',
    'wednesday': 'wednesday',
    'huwebes': 'thursday',
    'thursday': 'thursday',
    'biyernes': 'friday',
    'friday': 'friday',
    'sabado': 'saturday',
    'saturday': 'saturday',
    'linggo': 'sunday',
    'sunday': 'sunday',
}

FILIPINO_NUMBERS = {
    'isa': 1,
    'uno': 1,
    'one': 1,
    'dalawa': 2,
    'dos': 2,
    'two': 2,
    'tatlo': 3,
    'tres': 3,
    'three': 3,
    'apat': 4,
    'kwatro': 4,
    'four': 4,
    'lima': 5,
    'singko': 5,
    'five': 5,
    'anim': 6,
    'sais': 6,
    'six': 6,
    'pito': 7,
    'siete': 7,
    'seven': 7,
    'walo': 8,
    'otso': 8,
    'eight': 8,
    'siyam': 9,
    'nueve': 9,
    'nine': 9,
    'diez': 10,
    'sampu': 10,
    'ten': 10,
    'onse': 11,
    'eleven': 11,
    'dose': 12,
    'twelve': 12,
}


class VoiceCommandService:
    def __init__(self, user, request=None):
        self.user = user
        self.request = request

    def execute(self, transcript):
        original_transcript = transcript
        corrected_transcript = self.normalize_transcript(transcript)
        classification = AIService(self.user).classify_voice_intent(
            corrected_transcript,
            context_phrases=self._context_phrases(),
        )
        intent = classification.get('intent') or 'create_task'
        confidence = float(classification.get('confidence') or 0.55)

        handlers = {
            'navigate': self._navigate,
            'create_task': self._create_task,
            'update_task': self._update_task,
            'complete_task': self._complete_task,
            'delete_task': self._delete_task,
            'filter_tasks': self._filter_tasks,
            'search_tasks': self._search_tasks,
            'export_tasks': self._export_tasks,
            'task_summary': self._task_summary,
            'how_to': self._how_to,
            'logout': self._logout,
        }
        handler = handlers.get(intent, self._create_task)
        result = handler(corrected_transcript, classification)
        result.setdefault('intent', intent)
        result.setdefault('confidence', confidence)
        result.setdefault('transcript', original_transcript)
        result.setdefault('corrected_transcript', corrected_transcript)

        stored_result = json.loads(json.dumps(result, default=str))
        VoiceCommand.objects.create(
            user=self.user,
            transcript=original_transcript,
            intent=result.get('intent', intent),
            confidence=result.get('confidence', confidence),
            action=result.get('action', ''),
            response_message=result.get('message', ''),
            success=result.get('success', False),
            metadata=stored_result,
        )
        self._update_analytics(result.get('success', False))
        return result

    def normalize_transcript(self, transcript):
        normalized = transcript.strip()
        normalized = self._apply_static_corrections(normalized)
        normalized = self._apply_context_phrase_corrections(normalized)
        return re.sub(r'\s+', ' ', normalized).strip()

    def _apply_static_corrections(self, transcript):
        corrected = transcript
        for wrong, right in VOICE_CORRECTIONS.items():
            corrected = re.sub(rf'\b{re.escape(wrong)}\b', right, corrected, flags=re.IGNORECASE)
        return corrected

    def _apply_context_phrase_corrections(self, transcript):
        corrected = transcript
        for phrase in self._context_phrases():
            words = phrase.split()
            if len(words) > 5:
                continue
            window_size = len(words)
            tokens = corrected.split()
            for index in range(0, max(len(tokens) - window_size + 1, 0)):
                candidate = ' '.join(tokens[index:index + window_size])
                if candidate.lower() == phrase.lower():
                    continue
                score = SequenceMatcher(None, candidate.lower(), phrase.lower()).ratio()
                if score >= 0.78:
                    tokens[index:index + window_size] = [phrase]
                    corrected = ' '.join(tokens)
                    break
        return corrected

    def _context_phrases(self):
        task_titles = list(
            Task.objects.filter(user=self.user)
            .values_list('title', flat=True)
            .order_by('-updated_at')[:30]
        )
        categories = ['School', 'Work', 'Personal', 'Others']
        return list(dict.fromkeys([*KNOWN_VOICE_PHRASES, *task_titles, *categories]))

    def parse_task_payload(self, transcript):
        text = transcript.lower().strip()
        now = timezone.localtime(timezone.now())

        # Priority detection (supports 'high', 'medium', 'low')
        priority = 'medium'
        priority_aliases = {
            'high': ['high', 'mataas', 'urgent', 'importante'],
            'medium': ['medium', 'katamtaman', 'normal'],
            'low': ['low', 'mababa'],
        }
        for value, words in priority_aliases.items():
            pattern = r'\b(?:priority|prayoridad)?\s*(' + '|'.join(re.escape(word) for word in words) + r')\s*(?:priority|prayoridad)?\b'
            if re.search(pattern, text):
                priority = value
                text = re.sub(pattern, '', text).strip()
                break

        category_label = self._extract_category(text)
        if category_label:
            text = re.sub(
                r'\b(category|kategorya|sa|para sa|under|in)\s+'
                r'(school|paaralan|eskwela|skwela|klase|work|trabaho|opisina|personal|sarili|pansarili|others|other|iba(?:\s+pa)?)\b',
                '',
                text,
                flags=re.IGNORECASE,
            ).strip()

        # Relative date parsing: 'in 2 days', 'next week', 'this evening', 'tomorrow', 'today'
        task_date = now.date()
        relative_days = re.search(r'\bin\s+(\d+)\s+days?\b', text)
        if relative_days:
            days = int(relative_days.group(1))
            task_date = now.date() + timedelta(days=days)
            text = text.replace(relative_days.group(0), '').strip()
        elif 'next week' in text:
            task_date = now.date() + timedelta(days=7)
            text = text.replace('next week', '').strip()
        elif 'this evening' in text or 'tonight' in text:
            # leave date as today but adjust time later
            text = text.replace('this evening', '').replace('tonight', '').strip()
        elif 'tomorrow' in text or 'bukas' in text:
            task_date = now.date() + timedelta(days=1)
            text = text.replace('tomorrow', '').replace('bukas', '').strip()
        elif 'today' in text or 'ngayon' in text or 'mamaya' in text:
            text = text.replace('today', '').replace('ngayon', '').replace('mamaya', '').strip()
        else:
            weekday_date = self._parse_weekday(text, now)
            if weekday_date:
                task_date = weekday_date
                text = re.sub(
                    r'\b(next\s+|sa\s+susunod\s+na\s+|sa\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday|lunes|martes|miyerkules|huwebes|biyernes|sabado|linggo)\b',
                    '',
                    text,
                    flags=re.IGNORECASE,
                ).strip()
            else:
                # Try to parse explicit date phrases like 'on April 5' or 'April 5, 2026'
                date_match = re.search(r'(?:on\s+)?(\w+\s+\d{1,2}(?:,?\s*\d{4})?)', text)
                if date_match:
                    try:
                        parsed_date = date_parser.parse(date_match.group(1), fuzzy=True)
                        task_date = parsed_date.date()
                        if task_date.year < now.year:
                            task_date = task_date.replace(year=now.year)
                        text = text[:date_match.start()] + text[date_match.end():]
                    except (ValueError, OverflowError):
                        pass

        # Time parsing: support 'at 5pm', '5:30 pm', 'in 2 hours', 'noon', 'midnight', 'this evening'
        time_value = '09:00'
        # 'in N hours' relative time
        rel_hours = re.search(r'\bin\s+(\d+)\s+hours?\b', text)
        if rel_hours:
            hrs = int(rel_hours.group(1))
            future = now + timedelta(hours=hrs)
            time_value = future.strftime('%H:%M')
            text = text.replace(rel_hours.group(0), '').strip()
        else:
            patterns = [
                r'\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b',
                r'\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b',
                r'\bat\s+(\d{1,2})(?::(\d{2}))?\b',
                r'\b(\d{1,2}):(\d{2})\b',
            ]
            matched = False
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    groups = match.groups()
                    hour = int(groups[0])
                    minute = int(groups[1]) if groups[1] and groups[1].isdigit() else 0
                    ampm = groups[2].lower() if len(groups) > 2 and groups[2] else None
                    if ampm == 'pm' and hour != 12:
                        hour += 12
                    elif ampm == 'am' and hour == 12:
                        hour = 0
                    time_value = f'{hour:02d}:{minute:02d}'
                    text = text[:match.start()] + text[match.end():]
                    matched = True
                    break
            if not matched:
                filipino_time = self._parse_filipino_time(text)
                if filipino_time:
                    time_value, matched_text = filipino_time
                    text = text.replace(matched_text, '').strip()
                elif 'noon' in text or 'tanghali' in text:
                    time_value = '12:00'
                    text = text.replace('noon', '').replace('tanghali', '').strip()
                elif 'midnight' in text:
                    time_value = '00:00'
                    text = text.replace('midnight', '').strip()
                elif any(word in transcript.lower() for word in ['this evening', 'tonight', 'gabi', 'hapon']):
                    # favor 18:00 for evening
                    time_value = '18:00'

        # Title cleanup
        title = re.sub(
            r"\b(add|create|schedule|set|remind|me|to|a|an|the|at|on|today|tomorrow|am|pm|"
            r"category|under|school|work|personal|others|other|"
            r"gawa|gumawa|dagdag|idagdag|magdagdag|paalala|ng|sa|ako|bukas|ngayon|mamaya|"
            r"para|kategorya|prayoridad|mataas|katamtaman|mababa|importante|"
            r"alas|umaga|hapon|gabi|tanghali|susunod|na|in)\b",
            '',
            text,
        )
        title = re.sub(r'\s+', ' ', title).strip(' :')

        return {
            'title': title.capitalize() if title else 'Untitled Task',
            'date': task_date.isoformat(),
            'time': time_value,
            'priority': priority,
            'status': 'pending',
            'category_label': category_label,
        }

    def _extract_category(self, text):
        for word in ['school', 'paaralan', 'eskwela', 'skwela', 'klase', 'work', 'trabaho', 'opisina', 'personal', 'sarili', 'pansarili', 'others', 'other', 'iba', 'iba pa']:
            if re.search(rf'\b(?:category|kategorya|in|under|sa|para sa)?\s*{word}\b', text, re.IGNORECASE):
                return normalize_category_name(word)
        return ''

    def _parse_weekday(self, text, now):
        weekdays = {
            'monday': 0,
            'tuesday': 1,
            'wednesday': 2,
            'thursday': 3,
            'friday': 4,
            'saturday': 5,
            'sunday': 6,
        }
        match = re.search(
            r'\b(next\s+|sa\s+susunod\s+na\s+|sa\s+)?'
            r'(monday|tuesday|wednesday|thursday|friday|saturday|sunday|lunes|martes|miyerkules|huwebes|biyernes|sabado|linggo)\b',
            text,
            re.IGNORECASE,
        )
        if not match:
            return None
        weekday = FILIPINO_WEEKDAYS.get(match.group(2).lower(), match.group(2).lower())
        target = weekdays[weekday]
        days = (target - now.date().weekday()) % 7
        if days == 0 or match.group(1):
            days += 7
        return now.date() + timedelta(days=days)

    def _parse_filipino_time(self, text):
        match = re.search(
            r'\balas\s+(\d{1,2}|[a-z]+)(?:\s+(?:y\s+)?(?:media|trenta))?\s*(?:ng\s+)?(umaga|hapon|gabi)?\b',
            text,
            re.IGNORECASE,
        )
        if not match:
            return None
        hour_text = match.group(1).lower()
        hour = int(hour_text) if hour_text.isdigit() else FILIPINO_NUMBERS.get(hour_text)
        if not hour or hour > 12:
            return None
        minute = 30 if any(word in match.group(0).lower() for word in ['media', 'trenta']) else 0
        period = match.group(2)
        if period in ['hapon', 'gabi'] and hour != 12:
            hour += 12
        elif period == 'umaga' and hour == 12:
            hour = 0
        return f'{hour:02d}:{minute:02d}', match.group(0)

    def _create_task(self, transcript, classification):
        payload = self.parse_task_payload(transcript)
        payload = self._apply_ai_task_fields(payload, classification)
        serializer = TaskSerializer(data=payload, context={'request': self._serializer_request()})
        serializer.is_valid(raise_exception=True)
        task = serializer.save(user=self.user)
        task_data = TaskSerializer(task).data
        return {
            'success': True,
            'action': 'create_task',
            'message': f'Task added: {task.title}',
            'task': task_data,
            'result': task_data,
        }

    def _update_task(self, transcript, classification):
        task = self._find_task(classification.get('query') or self._update_query(transcript))
        if not task:
            return self._not_found('update')

        payload = self.parse_task_payload(transcript)
        payload = self._apply_ai_task_fields(payload, classification)
        text = transcript.lower()
        changed = []
        if self._has_date_signal(text) or classification.get('date'):
            task.date = date.fromisoformat(payload['date'])
            changed.append('date')
        if self._has_time_signal(text) or classification.get('time'):
            task.time = time.fromisoformat(payload['time']) if payload.get('time') else None
            changed.append('time')
        if 'priority' in text or any(word in text for word in ['urgent', 'important']) or classification.get('priority'):
            task.priority = payload['priority']
            changed.append('priority')
        if payload.get('category_label') and (classification.get('category') or self._extract_category(text)):
            serializer = TaskSerializer(task, data={'category_label': payload['category_label']}, partial=True, context={'request': self._serializer_request()})
            serializer.is_valid(raise_exception=True)
            task = serializer.save()
            changed.append('category')
        if not changed:
            return {
                'success': False,
                'action': 'update_task',
                'message': 'Tell me what to change, such as date, time, priority, or category.',
            }
        task.save()
        return {
            'success': True,
            'action': 'update_task',
            'message': f'Updated {", ".join(changed)} for: {task.title}',
            'task': TaskSerializer(task).data,
        }

    def _apply_ai_task_fields(self, payload, classification):
        if classification.get('title'):
            payload['title'] = classification['title'].strip().capitalize()
        if classification.get('date'):
            try:
                date.fromisoformat(classification['date'])
                payload['date'] = classification['date']
            except (TypeError, ValueError):
                pass
        if classification.get('time'):
            try:
                parsed = time.fromisoformat(classification['time'])
                payload['time'] = parsed.strftime('%H:%M')
            except (TypeError, ValueError):
                pass
        if classification.get('priority') in ['low', 'medium', 'high']:
            payload['priority'] = classification['priority']
        if classification.get('category') in ['School', 'Work', 'Personal', 'Others']:
            payload['category_label'] = classification['category']
        return payload

    def _update_query(self, transcript):
        text = re.sub(r'\b(update|change|move|reschedule|edit|palitan|ilipat)\b', '', transcript.lower()).strip()
        split_match = re.split(r'\b(to|on|at|priority|category|under|in)\b', text, maxsplit=1)
        return split_match[0].strip(' :') if split_match else text

    def _has_date_signal(self, text):
        return any(word in text for word in ['today', 'tomorrow', 'bukas', 'ngayon', 'mamaya', 'next week']) or bool(
            re.search(r'\b(next\s+|sa\s+susunod\s+na\s+|sa\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday|lunes|martes|miyerkules|huwebes|biyernes|sabado|linggo)\b|\b\w+\s+\d{1,2}\b|\bin\s+\d+\s+days?\b', text)
        )

    def _has_time_signal(self, text):
        return any(word in text for word in ['noon', 'midnight', 'tonight', 'evening', 'tanghali', 'umaga', 'hapon', 'gabi']) or bool(
            re.search(r'\bat\s+\d{1,2}|\balas\s+(\d{1,2}|[a-z]+)|\b\d{1,2}(:\d{2})?\s*(am|pm)\b|\b\d{1,2}:\d{2}\b|\bin\s+\d+\s+hours?\b', text)
        )

    def _complete_task(self, transcript, classification):
        task = self._find_task(classification.get('query') or transcript)
        if not task:
            return self._not_found('complete')
        task.status = 'completed'
        task.save(update_fields=['status', 'updated_at'])
        return {
            'success': True,
            'action': 'complete_task',
            'message': f'Marked complete: {task.title}',
            'task': TaskSerializer(task).data,
        }

    def _delete_task(self, transcript, classification):
        task = self._find_task(classification.get('query') or transcript)
        if not task:
            return self._not_found('delete')
        title = task.title
        task.delete()
        return {'success': True, 'action': 'delete_task', 'message': f'Deleted task: {title}'}

    def _filter_tasks(self, transcript, classification):
        target = (classification.get('target') or 'all').lower()
        today = timezone.localdate()
        queryset = Task.objects.filter(user=self.user).select_related('category')
        if target == 'today':
            queryset = queryset.filter(date=today)
        elif target == 'tomorrow':
            queryset = queryset.filter(date=today + timedelta(days=1))
        elif target == 'completed':
            queryset = queryset.filter(status='completed')
        elif target == 'overdue':
            queryset = queryset.filter(status='pending', date__lt=today)
        elif target == 'high':
            queryset = queryset.filter(status='pending', priority='high')
        elif target and target not in ['all', 'categories']:
            queryset = queryset.filter(category__name__icontains=target)
        tasks = list(queryset[:25])
        return {
            'success': True,
            'action': 'filter_tasks',
            'target': target,
            'message': f'Found {len(tasks)} matching task(s).',
            'tasks': TaskSerializer(tasks, many=True).data,
        }

    def _search_tasks(self, transcript, classification):
        query = classification.get('query') or transcript
        query = re.sub(r'\b(search|find|hanapin|task|for)\b', '', query.lower()).strip()
        tasks = Task.objects.filter(user=self.user, title__icontains=query).select_related('category')[:25]
        return {
            'success': True,
            'action': 'search_tasks',
            'query': query,
            'message': f'Found {len(tasks)} result(s) for "{query}".',
            'tasks': TaskSerializer(tasks, many=True).data,
        }

    def _task_summary(self, transcript, classification):
        summary = AIService(self.user).summarize_tasks()
        return {
            'success': True,
            'action': 'task_summary',
            'message': summary.get('summary', 'Summary is ready.'),
            'result': summary,
        }

    def _how_to(self, transcript, classification):
        guide = {
            'summary': 'Use short commands with an action, task title, date, time, priority, and category.',
            'recommendations': [
                'Add: "Add math quiz tomorrow at 3 PM priority high category School."',
                'Update: "Move math quiz to Friday at 10 AM" or "Change math quiz priority high."',
                'Finish/delete: "Complete math quiz" or "Delete math quiz."',
                'Categories are School, Work, Personal, and Others.',
                'Filipino cues include dagdag, gumawa, bukas, ngayon, tapusin, burahin, and hanapin.',
            ],
        }
        return {
            'success': True,
            'action': 'how_to',
            'message': guide['summary'],
            'result': guide,
        }

    def _export_tasks(self, transcript, classification):
        tasks = Task.objects.filter(user=self.user).select_related('category').order_by('date', 'time')
        return {
            'success': True,
            'action': 'export_tasks',
            'message': f'Prepared {tasks.count()} task(s) for export.',
            'tasks': TaskSerializer(tasks, many=True).data,
        }

    def _navigate(self, transcript, classification):
        target = classification.get('target') or 'dashboard'
        return {
            'success': True,
            'action': 'navigate',
            'target': target,
            'message': f'Opening {target}.',
        }

    def _logout(self, transcript, classification):
        if self.request:
            logout(self.request)
        return {'success': True, 'action': 'logout', 'message': 'Logged out successfully.'}

    def _find_task(self, query):
        cleaned = re.sub(
            r'\b(complete|done|finish|delete|remove|task|old|reminder|tapusin|burahin|tanggalin|alisin|kumpleto|markahan)\b',
            '',
            query.lower(),
        ).strip(' :')
        queryset = Task.objects.filter(user=self.user, status='pending').order_by('date', 'time')
        if cleaned:
            match = queryset.filter(title__icontains=cleaned).first()
            if match:
                return match
        return queryset.first()

    def _not_found(self, action):
        return {
            'success': False,
            'action': f'{action}_task',
            'message': f'I could not find a task to {action}.',
        }

    def _update_analytics(self, success):
        analytics, _ = VoiceAnalytics.objects.get_or_create(user=self.user)
        analytics.total_commands += 1
        if success:
            analytics.successful_commands += 1
        analytics.last_command_at = timezone.now()
        analytics.save(update_fields=['total_commands', 'successful_commands', 'last_command_at', 'updated_at'])

    def _serializer_request(self):
        if self.request:
            return self.request

        class RequestProxy:
            pass

        proxy = RequestProxy()
        proxy.user = self.user
        return proxy
