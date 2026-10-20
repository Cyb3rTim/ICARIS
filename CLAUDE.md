# ICARIS: notes for Claude Code

ICARIS is a Django 5.2 GRC platform: ATO tracking on the NIST SP 800-53 Rev 5
catalog, POA&Ms, continuous monitoring and evidence management.

## Run it locally (trial run)

Work inside this repository only. Do not touch files outside it.

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                      # then set DJANGO_SECRET_KEY (see the file)
export DJANGO_DEBUG=true
python manage.py migrate
python manage.py seed_demo                # prints demo logins and a random password
python manage.py runserver 127.0.0.1:8000 # bind to localhost only
```

Demo users: `admin` (superuser), `isso`, `analyst`, `auditor`. They share the
password `seed_demo` prints. Open http://127.0.0.1:8000.

Docker alternative: `docker compose up --build` (needs `POSTGRES_PASSWORD`
and `DJANGO_SECRET_KEY` in `.env`), then
`docker compose exec web python manage.py seed_demo --force`.

## Checks before committing

```bash
ruff check .
DJANGO_DEBUG=true python manage.py makemigrations --check --dry-run
pytest --cov                              # uses grc_project/settings_test.py
bandit -c pyproject.toml -r grc_dashboard grc_project ato
```

## Layout

- `grc_project/`: settings (env-driven; see `.env.example`), URLs, test settings
- `grc_dashboard/`: dashboard, POA&Ms (`Issue`), ConMon (`Risk`), artifacts, roles, audit log, `seed_demo`
- `ato/`: systems, 800-53 catalog import (`import_oscal_catalog`), control implementations, authorization packages

## Conventions

- Write actions require a model permission granted via the ISSO / Analyst /
  Auditor roles in `grc_dashboard/roles.py`; add tests for allowed and denied cases.
- Uploaded files go through `grc_dashboard/validators.py` and are served only
  by authenticated views, never from /media/.
- Front-end assets are vendored under `grc_dashboard/static/vendor/`; do not add CDN links.
- `seed_demo` creates demo accounts: never run it against a real database.
