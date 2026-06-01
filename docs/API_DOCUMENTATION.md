# API Documentation

All protected endpoints use Django session authentication.

## Accounts

- `POST /api/accounts/register/`
- `POST /api/accounts/login/`
- `POST /api/accounts/logout/`
- `GET /api/accounts/profile/`
- `PATCH /api/accounts/profile/`
- `POST /api/accounts/change-password/`

## Tasks

- `GET /api/tasks/`
- `POST /api/tasks/`
- `GET /api/tasks/<id>/`
- `PATCH /api/tasks/<id>/`
- `DELETE /api/tasks/<id>/`
- `GET /api/tasks/summary/`
- `GET /api/tasks/today/`
- `GET /api/tasks/upcoming/`
- `POST /api/tasks/from-voice/`

Task query parameters:

- `view=today|upcoming|overdue|completed|high`
- `status=pending|completed`
- `priority=low|medium|high`
- `category=<name>`
- `search=<text>`

## Voice

`POST /api/voice/command/`

Request:

```json
{"transcript": "Complete task project deadline"}
```

Response:

```json
{
  "success": true,
  "intent": "complete_task",
  "confidence": 0.82,
  "action": "complete_task",
  "message": "Marked complete: Project deadline"
}
```

## AI

- `GET /api/ai/summary/`
- `POST /api/ai/summary/`

Returns a summary, recommendations, priority suggestions, and whether external AI was used.

## MCP-Style Tools

- `GET /api/tools/`
- `POST /api/tools/task-analyzer/execute/`
- `POST /api/tools/task-recommender/execute/`
- `POST /api/tools/smart-scheduler/execute/`
- `POST /api/tools/priority-optimizer/execute/`
