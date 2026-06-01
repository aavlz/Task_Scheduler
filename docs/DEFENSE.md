# Assessment Defense Notes

## Demo Flow

1. Register or log in.
2. Create a task manually.
3. Create a task with the mic command.
4. Complete and filter tasks.
5. Show dashboard and calendar updates.
6. Run AI Summary.
7. Run Task Analyzer.
8. Show Railway URL and PostgreSQL configuration.
9. Show Git commit history and tests.

## Technical Points

- Django REST Framework provides authenticated JSON APIs.
- PostgreSQL is configured through `DATABASE_URL` for Railway.
- The mic button uses Web Speech API in the browser.
- The backend command processor supports structured intent execution and records analytics.
- AI has a rule-based fallback, so the app remains usable without an API key.
- MCP-style tools expose advanced productivity analysis through `/api/tools/`.
