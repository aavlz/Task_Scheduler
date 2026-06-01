# Railway Deployment and PostgreSQL Migration

This project is configured to use SQLite locally and PostgreSQL in production when `DATABASE_URL` is present.

## Files already prepared

- `requirements.txt` includes `dj-database-url` and `psycopg[binary]`.
- `vast_config/settings.py` reads `DATABASE_URL`, uses Whitenoise for static files, and trusts `RAILWAY_PUBLIC_DOMAIN`.
- `railway.json` runs `collectstatic` during build and runs `migrate` before starting Gunicorn.
- `Procfile` binds Gunicorn to Railway's `$PORT`.

## Local preparation

1. Run checks:

   ```bash
   python manage.py check
   python manage.py test
   ```

2. Confirm all migrations exist:

   ```bash
   python manage.py makemigrations --check --dry-run
   ```

3. Export SQLite data if you need to preserve local/demo data:

   ```bash
   python manage.py dumpdata --natural-foreign --natural-primary --exclude contenttypes --exclude auth.permission --indent 2 > data.json
   ```

## Optional local PostgreSQL rehearsal

1. Create a PostgreSQL database locally.
2. Set `DATABASE_URL` in `.env`, for example:

   ```env
   DATABASE_URL=postgresql://postgres:password@localhost:5432/vast
   ```

3. Apply migrations and load data:

   ```bash
   python manage.py migrate
   python manage.py loaddata data.json
   python manage.py runserver
   ```

## Railway setup

1. Push the project to GitHub.
2. In Railway, create a new project from the GitHub repository.
3. Add a PostgreSQL database service to the project.
4. Make sure the web service has a `DATABASE_URL` variable from the PostgreSQL service.
5. Set these web service variables:

   ```env
   DEBUG=False
   SECRET_KEY=<long-random-secret>
   ALLOWED_HOSTS=<your-app>.up.railway.app
   CSRF_TRUSTED_ORIGINS=https://<your-app>.up.railway.app
   DEFAULT_FROM_EMAIL=<verified-sendgrid-sender>
   EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
   EMAIL_HOST=smtp.sendgrid.net
   EMAIL_PORT=587
   EMAIL_HOST_USER=apikey
   EMAIL_HOST_PASSWORD=<sendgrid-api-key>
   EMAIL_USE_TLS=True
   EMAIL_USE_SSL=False
   EMAIL_TIMEOUT=10
   GEMINI_API_KEY=<optional>
   OPENAI_API_KEY=<optional>
   ```

   If registration hangs or Railway logs show a worker timeout while connecting
   to SMTP, switch to the HTTPS SendGrid backend instead:

   ```env
   EMAIL_BACKEND=accounts.email_backends.SendGridAPIEmailBackend
   SENDGRID_API_KEY=<sendgrid-api-key>
   DEFAULT_FROM_EMAIL=<verified-sendgrid-sender>
   EMAIL_TIMEOUT=10
   ```

6. Deploy. `railway.json` will run:

   ```bash
   python manage.py collectstatic --noinput
   python manage.py migrate
   gunicorn vast_config.wsgi:application --bind 0.0.0.0:$PORT --log-file -
   ```

## Migrating existing SQLite data to Railway PostgreSQL

1. Before deployment, export local SQLite data:

   ```bash
   python manage.py dumpdata --natural-foreign --natural-primary --exclude contenttypes --exclude auth.permission --indent 2 > data.json
   ```

2. Deploy to Railway and let migrations run.
3. Upload/import `data.json` using one of these approaches:

   ```bash
   railway run python manage.py loaddata data.json
   ```

   Or run the same command in Railway's web service shell if available.

4. Create an admin user if needed:

   ```bash
   railway run python manage.py createsuperuser
   ```

## After deployment test list

- Register a new account and verify email through SendGrid.
- Log in and create a task.
- Confirm task category colors render.
- Edit a task reminder.
- Mark a task completed and check notifications.
- Test forgot password email link.
- Open Django admin with the superuser account.

## Important production note

User-uploaded profile photos currently use Django local media storage. Railway containers can redeploy and lose filesystem uploads, so production profile photos should eventually move to persistent object storage such as Cloudinary, S3, or a Railway volume.