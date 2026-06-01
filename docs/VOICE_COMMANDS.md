# Voice Commands

The frontend uses the browser Web Speech API and sends transcripts to `/api/voice/command/`.

Supported action groups:

- Navigation: `Go to dashboard`, `Show calendar`, `Open settings`, `Go to profile`.
- Creation: `Create task buy groceries tomorrow at 8 AM priority high`.
- Actions: `Complete task project deadline`, `Delete task old reminder`.
- Filters: `Show my tasks`, `List completed tasks`, `Show overdue tasks`, `Show high priority tasks`.
- Search/export: `Search for meeting`, `Export my tasks`.
- AI: `Give me a summary`.
- System: `Logout`.

The backend returns `intent`, `confidence`, `action`, `message`, and optional `task`, `tasks`, or `result` payloads.
