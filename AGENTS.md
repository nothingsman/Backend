# AGENTS.md

Guidance for AI coding agents working in this Django project.

## Project Snapshot

This repository is a cookiecutter-style Django application named `core`. It is primarily a REST API backend, with Django plumbing in `config/` and feature code in `core/`. The main local domain is the `users` app, and the codebase already includes templates, static assets, translations, docs, Celery, REST API support, and Docker-based local/production setups.

When in doubt, follow the existing patterns in the codebase and link to the existing documentation instead of re-explaining it here.

## Start Here

Read the files that define the project’s conventions before making changes:

- [README.md](README.md) for the basic runtime and developer commands.
- [pyproject.toml](pyproject.toml) for tool configuration, formatting, typing, and test settings.
- [justfile](justfile) for the repo’s container and management command shortcuts.
- [docs/howto.rst](docs/howto.rst) and [docs/conf.py](docs/conf.py) for documentation behavior.
- [locale/README.md](locale/README.md) for translation workflows.

## Repository Layout

Use the existing boundaries in the repository:

- `config/` owns project wiring: settings, ASGI/WSGI, Celery, URL routing, and websocket setup.
- `core/` is the main app package and contains local apps, shared templates, static assets, and reusable project-specific pieces.
- `core/users/` is the primary feature app and the clearest example of how the project expects models, forms, views, APIs, tests, and factories to be organized.
- `core/contrib/sites/` contains the custom Site migration path used by the project.
- `docs/` is Sphinx documentation, not application code.
- `locale/` contains translation catalogs.

Do not create a new top-level app structure unless the existing layout clearly does not fit the task.

## Django Architecture

The project uses a layered settings structure:

- `config/settings/base.py` defines shared settings and app registration.
- `config/settings/local.py` holds developer-only settings.
- `config/settings/production.py` holds production settings.
- `config/settings/test.py` holds test-specific settings.

App registration follows the pattern `DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS`. Keep new local apps in the local section and preserve the separation between Django apps, third-party apps, and project code.

The project uses a custom user model. Treat changes to authentication and user fields as high risk because many parts of the codebase assume the current user shape and URL patterns.

## User Domain Conventions

The `users` app establishes the main project conventions.

- The custom user model is `core.users.models.User`.
- Views are login-protected by default and usually operate on the current authenticated user.
- The API is intentionally self-scoped; user endpoints should generally expose the current user, not a global user directory.

When working in this app, reuse the existing patterns in `models.py`, `forms.py`, `views.py`, `api/views.py`, and `tests/factories.py` instead of inventing new conventions.

## Testing Expectations

Tests are part of the normal workflow and should be updated with the code change.

Run tests in the Docker environment by default. Do not use host-local pytest for normal verification in this repo unless the user explicitly asks for it or Docker is unavailable.

- Prefer `docker compose -f docker-compose.local.yml run --rm django pytest` for the full test suite.
- Prefer the narrowest useful `docker compose -f docker-compose.local.yml run --rm django pytest path/to/test_file.py` or `docker compose -f docker-compose.local.yml run --rm django pytest --filter ...` style invocation when the change is localized.
- Never run bare `pytest` for normal verification in this repo. Use the Docker form above unless the user explicitly asks for host-local pytest.
- Use the existing `core/users/tests/` layout as the model for new app tests.
- Use factory-boy factories from `core/users/tests/factories.py` or similar app-local factories instead of ad hoc object setup when possible.
- Keep tests close to the app they cover and name them to match the existing `test_*.py` pattern.

If you change behavior, add or update tests for the touched slice before finishing.

## Tooling And Quality Gates

The project’s developer tooling is already configured in `pyproject.toml` and should be followed rather than overridden.

- Use `docker compose -f docker-compose.local.yml run --rm django uv run mypy core` for type checking.
- Use Ruff for Python linting and formatting according to the repo configuration.
- Run Ruff from the project virtualenv, not from an arbitrary global install: `source .venv/bin/activate && ruff check . --exclude .agents`.
- When running focused Ruff checks, still exclude `.agents` explicitly.
- Use `djlint` conventions for Django templates.
- Respect the migration exclusion in Ruff and the existing mypy Django/DRF plugins.
- Prefer explicit type hints and explicit return types in Python code.
- Keep control-flow braces and style consistent with the surrounding codebase.

If you touch Python code, expect to format or lint according to the repo configuration before considering the work done.

## Commands And Runtime Workflow

Use the repo’s existing commands instead of inventing new ones.

- Use Docker-based commands by default for this repository, including focused test and verification runs.
- For verification, the default split is: Docker for `pytest`, local virtualenv for `ruff check`, and explicit `.agents` exclusion for Ruff.
- Use `just` for common container and management tasks.
- Use `just build`, `just up`, `just down`, `just logs`, and `just manage ...` when working with the Dockerized local environment.
- Use `docker compose -f docker-compose.local.yml run --rm django uv run python manage.py createsuperuser` for superuser creation when needed.
- Use the Celery commands documented in [README.md](README.md) for worker and beat processes.
- Use Docker-based commands when you need to match the local development environment.

Do not add new helper scripts unless the existing tools cannot do the job cleanly.

## Templates, Static Files, And Frontend Assets

Shared templates live in `core/templates/` and project assets live in `core/static/`.

- Extend `base.html` where possible instead of duplicating layout markup.
- Keep template changes consistent with the existing Bootstrap-based shell.
- Reuse the central static asset pipeline rather than scattering new asset locations.
- Preserve the current naming and structure for page, user, and account templates.

If you change templates, follow the repo’s djLint settings and the existing block structure.

## Documentation And Translations

Documentation and translations are first-class parts of the repo.

- Update docs only when a behavior change affects developer workflow or project usage.
- Keep Sphinx docs under `docs/` and avoid duplicating application logic there.
- Keep translation changes under `locale/` and follow the commands in [locale/README.md](locale/README.md).
- Do not create new documentation files unless the task explicitly asks for them.

## Database And Migrations

Be careful with schema changes.

- Use Django migrations for model changes.
- Treat changes to existing model fields as destructive if they alter the current shape or behavior.
- Preserve existing field behavior, defaults, nullability, and constraints unless the task explicitly calls for a schema change.
- Review any migration impact on the custom user model, auth flows, or the custom Site migration path.

## API Conventions

The project already includes DRF and Spectacular support.

- Prefer existing serializer and viewset patterns in `core/users/api/`.
- Keep API behavior aligned with the current self-service design unless the task explicitly changes that contract.
- Reuse the current authentication and permission patterns rather than adding parallel approaches.

## Safety And Change Management

Follow a minimal, local change strategy.

- Start from the closest owning abstraction, not a broad rewrite.
- Preserve unrelated user changes in the workspace.
- Avoid changing dependencies, base architecture, or file layout without a strong reason.
- Prefer reusing existing code paths, factories, templates, and settings over introducing new infrastructure.
- If a change touches authentication, settings, containers, or deployment, double-check the surrounding files before editing.

## Good Agent Behavior In This Repo

- Make changes that fit the current code style and app boundaries.
- Add tests for changed behavior.
- Keep explanations short and concrete.
- Link to existing docs instead of re-embedding them.
- If a task spans a specific subsystem, inspect the local files first and then edit only the touched slice.
- Do not generate new UI, pages, or frontend flows unless the user explicitly asks for UI work.
- Prefer API, model, viewset, serializer, and admin changes over template or asset changes when the request is ambiguous.

## Useful References

- [README.md](README.md)
- [pyproject.toml](pyproject.toml)
- [justfile](justfile)
- [docs/howto.rst](docs/howto.rst)
- [locale/README.md](locale/README.md)
- [config/settings/base.py](config/settings/base.py)
- [core/users/models.py](core/users/models.py)
- [core/users/views.py](core/users/views.py)
- [core/users/forms.py](core/users/forms.py)
- [core/users/tests/factories.py](core/users/tests/factories.py)
