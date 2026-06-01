# core

Behold My Awesome Project!

[![Built with Cookiecutter Django](https://img.shields.io/badge/built%20with-Cookiecutter%20Django-ff69b4.svg?logo=cookiecutter)](https://github.com/cookiecutter/cookiecutter-django/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

License: MIT

## Settings

Moved to [settings](https://cookiecutter-django.readthedocs.io/en/latest/1-getting-started/settings.html).

### SMS Backend (Telerivet)

Parent OTP (`/auth/otp/request/`) and parent invitation (`/api/parents/invite/`)
use the configured SMS backend. To use Telerivet:

```
SMS_BACKEND=accounts.sms_backends.TelerivetSMSBackend
TELERIVET_API_KEY=your_telerivet_api_key
TELERIVET_PROJECT_ID=your_telerivet_project_id
TELERIVET_TIMEOUT_SECONDS=10
```

Phone numbers should be provided in international format, e.g. `+2519XXXXXXXX`.

## Basic Commands

### Setting Up Your Users

- To create a **normal user account**, just go to Sign Up and fill out the form. Once you submit it, you'll see a "Verify Your E-mail Address" page. Go to your console to see a simulated email verification message. Copy the link into your browser. Now the user's email should be verified and ready to go.

- To create a **superuser account**, use this command:

      uv run python manage.py createsuperuser

For convenience, you can keep your normal user logged in on Chrome and your superuser logged in on Firefox (or similar), so that you can see how the site behaves for both kinds of users.

### Type checks

Running type checks with mypy:

    uv run mypy core

### MCP API docs server

This repo includes a small read-only MCP server that exposes the backend
OpenAPI schema for AI agents.

Run it over stdio with:

    uv run backend-api-docs-mcp

Or expose the same MCP server over HTTP from Django at:

    POST /api/mcp/

Example request:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {}
}
```

It exposes two MCP resources:

- `resource://backend-api-docs/openapi-schema`
- `resource://backend-api-docs/api-summary`

Optional environment variables:

- `BACKEND_API_SCHEMA_URL` to override the live schema URL
- `BACKEND_API_SCHEMA_FALLBACK_PATH` to use a local schema file if the backend is unavailable
- `BACKEND_API_SCHEMA_TIMEOUT_SECONDS` to change the live fetch timeout
- `BACKEND_API_SCHEMA_AUTH_HEADER`, `BACKEND_API_SCHEMA_AUTH_SCHEME`, and `BACKEND_API_SCHEMA_AUTH_TOKEN` for authenticated schema fetches

### Test coverage

To run the tests, check your test coverage, and generate an HTML coverage report:

    uv run coverage run -m pytest
    uv run coverage html
    uv run open htmlcov/index.html

#### Running tests with pytest

    uv run pytest

### Live reloading and Sass CSS compilation

Moved to [Live reloading and SASS compilation](https://cookiecutter-django.readthedocs.io/en/latest/2-local-development/developing-locally.html#using-webpack-or-gulp).

### Celery

This app comes with Celery.

To run a celery worker:

```bash
cd core
uv run celery -A config.celery_app worker -l info
```

Please note: For Celery's import magic to work, it is important _where_ the celery commands are run. If you are in the same folder with _manage.py_, you should be right.

To run [periodic tasks](https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html), you'll need to start the celery beat scheduler service. You can start it as a standalone process:

```bash
cd core
uv run celery -A config.celery_app beat
```

or you can embed the beat service inside a worker with the `-B` option (not recommended for production use):

```bash
cd core
uv run celery -A config.celery_app worker -B -l info
```

### Email Server

In development, it is often nice to be able to see emails that are being sent from your application. For that reason local SMTP server [Mailpit](https://github.com/axllent/mailpit) with a web interface is available as docker container.

Container mailpit will start automatically when you will run all docker containers.
Please check [cookiecutter-django Docker documentation](https://cookiecutter-django.readthedocs.io/en/latest/2-local-development/developing-locally-docker.html) for more details how to start all containers.

With Mailpit running, to view messages that are sent by your application, open your browser and go to `http://127.0.0.1:8025`

## Deployment

The following details how to deploy this application.

### Docker

See detailed [cookiecutter-django Docker documentation](https://cookiecutter-django.readthedocs.io/en/latest/3-deployment/deployment-with-docker.html).

Production now includes a MinIO service for the multipart media upload flow. Set
`S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_BUCKET`, `S3_REGION`,
`S3_INTERNAL_ENDPOINT`, and `S3_PUBLIC_ENDPOINT` in
`.envs/.production/.django`, and point the `uploads.kelem.app` DNS record at the
same Traefik entrypoint as `api.kelem.app`.
