# Local setup and testing

How to get this repo running and tested on a development machine. Written for the machine this
repo currently sits on: **Ubuntu 26.04 (WSL2)**.

> **Nothing in this document has been executed.** It is a recipe, verified against the repo, CI, and
> the official install guide — not a record of a completed setup. Start at "Blocker" below.

The official *deployment* guide is at
[docs.qhhoj.com/site/installation.md](https://docs.qhhoj.com/site/installation.md). It targets a
production server with uwsgi + nginx + supervisor. This document targets a dev box and adds the parts
that guide omits — testing, linting, and the Python version problem.

---

## Blocker: Python version

**Ubuntu 26.04 ships Python 3.14 only** (`/usr/bin/python3.14`). `requirements.txt` pins
`Django>=5.1,<5.2`, and **Django 5.1 supports Python 3.10–3.13**. CI (`.github/workflows/build.yml`)
uses **Python 3.11**.

Python 3.14 is not a supported configuration for this dependency set and has not been tried here.
Resolve this first — everything else depends on it.

**Option A — `uv` (recommended).** No root, no PPA, downloads a standalone CPython:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.11
uv venv --python 3.11 .venv
. .venv/bin/activate
```

**Option B — deadsnakes PPA.** May not have packages for `resolute` (26.04) yet; check before
relying on it:

```bash
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update && sudo apt install python3.11 python3.11-venv python3.11-dev
python3.11 -m venv .venv && . .venv/bin/activate
```

**Option C — try 3.14 anyway.** Untested. If you go this way, expect trouble from `mysqlclient`
(C extension) and the git-sourced forks in `requirements.txt`, and be prepared to unpin Django.
Note that CI will still run 3.11, so anything you fix for 3.14 is not validated by CI.

---

## Current state of this checkout

Everything below is currently **missing** and needs to be created:

| Thing | State |
|---|---|
| Python venv | none |
| `node_modules/` | none |
| `dmoj/local_settings.py` | does not exist |
| MariaDB / MySQL | not installed / inactive |
| Redis | not installed |
| `resources/libs` submodule | **not checked out** (`git submodule status` shows a `-` prefix) |
| Compiled CSS, `/static` | not built |
| Docker | not installed |

---

## 1. System packages

From the official guide, plus the MySQL headers needed to build `mysqlclient`:

```bash
sudo apt update
sudo apt install git gcc g++ make python3-dev python3-venv \
    libxml2-dev libxslt1-dev zlib1g-dev gettext curl pkg-config \
    redis-server mariadb-server libmysqlclient-dev
```

Node.js v22.22.1 is already present (the guide asks for 18+; CI uses 20).

## 2. Database

MySQL/MariaDB is **required** — see "Why not SQLite" below.

```bash
sudo mysql
```
```sql
CREATE DATABASE qhhoj DEFAULT CHARACTER SET utf8mb4 DEFAULT COLLATE utf8mb4_general_ci;
GRANT ALL PRIVILEGES ON qhhoj.* TO 'admin'@'localhost' IDENTIFIED BY '<password>';
```
```bash
# Several pages need timezone tables.
mariadb-tzinfo-to-sql /usr/share/zoneinfo | sudo mariadb -u root mysql
sudo service redis-server start
```

## 3. Submodule

`resources/libs` (jQuery and friends, from `github.com/qhhoj/site-assets`) is not checked out:

```bash
git submodule update --init --recursive
```

## 4. Python dependencies

```bash
. .venv/bin/activate           # from the Blocker section
pip install wheel
pip install -r requirements.txt
```

`additional_requirements.txt` (`uwsgi`, `websocket-client`) is only needed for production serving —
skip it in dev.

Note that `requirements.txt` pulls six packages from **git forks under `github.com/qhhoj`**
(`dmoj-wpadmin`, `django-fernet-fields`, `jsonfield`, `ansi2html`, `martor`, `markdown2`), so the
install needs network access to GitHub and is slower than a pure PyPI install.

## 5. `dmoj/local_settings.py`

This file is gitignored and does not exist. `dmoj/settings.py` `exec()`s it at the very bottom —
**never edit `settings.py` directly.** The upstream sample is
[here](https://github.com/qhhoj/docs/blob/master/sample_files/local_settings.py); a minimal dev
version:

```python
import os

SECRET_KEY = '<generate one>'  # python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
DEBUG = True
ALLOWED_HOSTS = ['localhost', '127.0.0.1']

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'qhhoj',
        'USER': 'admin',
        'PASSWORD': '<password>',
        'HOST': '127.0.0.1',
        'OPTIONS': {
            'charset': 'utf8mb4',
            'sql_mode': 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION',
        },
    },
}

CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}

# Static files / compressor
STATIC_ROOT = os.path.join(BASE_DIR, 'static')
COMPRESS_OUTPUT_DIR = 'cache'
STATICFILES_FINDERS += ('compressor.finders.CompressorFinder',)

# Where problem test data lives on disk. The judge servers mount this same path.
MEDIA_ROOT = '/tmp/media'
DMOJ_PROBLEM_DATA_ROOT = '/tmp/problem_data/'

# Celery
CELERY_BROKER_URL = 'redis://localhost:6379'
CELERY_RESULT_BACKEND = 'redis://localhost:6379'

# Leave the event server off until the rest works.
EVENT_DAEMON_USE = False

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

SITE_NAME = 'QHHOJ'
SITE_LONG_NAME = 'QHHOJ - Mission Impossible'
LANGUAGE_CODE = 'vi'
DEFAULT_USER_TIME_ZONE = 'Asia/Ho_Chi_Minh'
```

If you intend to touch the virtual-judge feature, also export
`EXTERNAL_JUDGE_ENCRYPTION_KEY` (see [qhhoj-features.md](qhhoj-features.md)) — it is read from the
environment, not from settings.

## 6. Assets and i18n

```bash
npm install
./make_style.sh                 # SCSS -> resources/style.css + resources/dark/style.css
./manage.py collectstatic
./manage.py compilemessages
./manage.py compilejsi18n
```

Skipping `make_style.sh` gives you an unstyled site — the compiled CSS is not in git.

## 7. Database schema and seed data

```bash
./manage.py migrate
./manage.py loaddata navbar
./manage.py loaddata language_small     # or language_all / language_more
./manage.py loaddata demo
```

> The `demo` fixture creates a superuser with username **and** password `admin`. Change or delete it
> if the machine is reachable by anyone else.

Create your own admin instead (this also creates the `Profile`, which plain `createsuperuser` does
not):

```bash
./manage.py adduser <username> <email> <password> --superuser --staff
```

## 8. Run it

```bash
./manage.py check
./manage.py runserver 0.0.0.0:8000
```

Optional additional processes, each in its own terminal:

```bash
./manage.py runbridged                  # judge bridge — needed to grade anything
celery -A dmoj_celery worker            # background tasks
node websocket/daemon.js                # live updates; needs websocket/config.js first
```

Only `runserver` is needed to browse the site and work on views/templates.

`websocket/config.js` is gitignored; create it as:

```js
const config = {
  get_host: "127.0.0.1",  get_port: 15100,
  post_host: "127.0.0.1", post_port: 15101,
  http_host: "127.0.0.1", http_port: 15102,
  long_poll_timeout: 29000,
};
export default config;
```

and set `EVENT_DAEMON_USE = True`, `EVENT_DAEMON_POST = 'ws://127.0.0.1:15101/'` in
`local_settings.py`.

---

## Testing

**CI is the only validated path** — reproduce it exactly. From `.github/workflows/build.yml`:

```bash
cp .ci.settings.py dmoj/local_settings.py     # ⚠ overwrites your dev settings — back it up first
./manage.py compilejsi18n
./manage.py test judge
```

With coverage, as CI does:

```bash
coverage run --source=. manage.py test judge
coverage xml
```

`.ci.settings.py` expects MySQL at `localhost:3306`, database `dmoj`, user `root`, password `root`.
Either provision that, or copy `.ci.settings.py` and edit the credentials rather than using it
verbatim.

**Where the tests are** — 123 tests across 11 files:

```
judge/models/tests/test_problem.py            judge/utils/tests/test_lazy.py
judge/models/tests/test_contest.py            judge/utils/tests/test_iterator.py
judge/models/tests/test_submission.py         judge/utils/tests/test_infinite_paginator.py
judge/models/tests/test_profile.py            judge/jinja2/markdown/test_markdown.py
judge/models/tests/test_blogpost.py           judge/test_external_judge_async.py
judge/models/tests/test_public_ranking_link.py
```

`judge/tests.py` is an empty stub — do not add tests there.

**Writing tests.** Use the helpers in `judge/models/tests/util.py`: `CommonDataMixin` (loads the
`language_all.json` fixture and creates a standard cast — superuser, several staff permission levels,
an org admin, a normal user, an anonymous user, and an `open` organization) plus `create_user`,
`create_organization`, `create_problem`, `create_solution`, `create_contest`,
`create_contest_participation`, `create_contest_problem`.

Run a subset the usual Django way:

```bash
./manage.py test judge.models.tests.test_problem
./manage.py test judge.models.tests.test_problem.ProblemTestCase.test_something
```

### Why not SQLite

`dmoj/settings.py` defaults to SQLite, which is misleading — the project is MySQL-only in practice:

| Code | Problem |
|---|---|
| `judge/dblock.py` | `LOCK TABLES` / `UNLOCK TABLES` |
| `judge/contest_format/vnoj.py` | Raw ranking SQL |
| `judge/contest_format/icpc.py`, `atcoder.py` | Raw cursor SQL |
| `judge/performance_points.py` | Raw SQL |
| `judge/admin/contest.py` | `TRUNCATE TABLE` |
| `judge/utils/raw_sql.py` | Custom `RawSQLJoin` against Django's SQL compiler |

The SQLite default is upstream inheritance, not a supported configuration.

---

## Linting

```bash
pip install flake8 flake8-import-order flake8-future-import flake8-commas flake8-logging-format flake8-quotes
flake8
```

All six plugins are required — CI installs exactly this list, and `.flake8` uses features from each.
Config summary:

- `max-line-length = 120`
- `import-order-style = pycharm`, `application-import-names = dmoj,judge,django_ace`
- Excluded: `dmoj/local_settings.py`, `dmoj/local_urls.py`, `.ci.settings.py`,
  `judge/migrations/*.py`, `fc_*`
- Per-file ignores: `F401,F403` in every `__init__.py`; `F403,F405` in
  `judge/management/commands/runmoss.py`

JavaScript (the `websocket/` directory only):

```bash
npm run format:check     # check
npm run format           # write
```

There is no pre-commit config; run these manually.

---

## Connecting a judge

Full guide: [docs.qhhoj.com/judge/setting_up_a_judge.md](https://docs.qhhoj.com/judge/setting_up_a_judge.md).
The judge server is a **separate repository** and is not in this tree. Summary:

1. Site side — create a Judge in Django admin (`/admin/judge/judge/`), set a name, hit *Regenerate*
   for the auth key. Confirm `BRIDGED_JUDGE_ADDRESS` (default `localhost:9999`) is reachable from
   wherever the judge will run, and that `bridged` is running.
2. Judge side — Docker is the supported route (**not installed on this machine**):

   ```bash
   docker run --name judge --network=host \
       -v /mnt/problems:/problems --cap-add=SYS_PTRACE \
       -d --restart=always \
       vnoj/judge-tiervnoj:latest \
       run -p 9999 -c /problems/judge.yml localhost -A 0.0.0.0 -a 12345
   ```

   with `/mnt/problems/judge.yml`:

   ```yaml
   id: <judge name>
   key: <judge authentication key>
   problem_storage_globs:
     - /problems/*
   ```

3. For a single-machine dev setup, point `DMOJ_PROBLEM_DATA_ROOT` and the container's `/problems`
   mount at the same directory so both site and judge see the same test data.

The PyPI judge package is **not supported** on the VNOJ/QHHOJ line — use Docker.

---

## Production, for contrast

None of the deployment config lives in this repo. Production is uwsgi + nginx, with supervisord
keeping `site`, `bridged`, `celery`, and `wsevent` alive. Sample files:
[`qhhoj/docs/sample_files`](https://github.com/qhhoj/docs/tree/master/sample_files) — `uwsgi.ini`,
`nginx.conf`, `site.conf`, `bridged.conf`, `celery.conf`, `wsevent.conf`, `local_settings.py`,
`judge_conf.yml`.

Before exposing anything: set `DEBUG = False`, set `ALLOWED_HOSTS`, and override `SECRET_KEY`,
`EVENT_DAEMON_SUBMISSION_KEY`, and `EVENT_DAEMON_CONTEST_KEY` — all three ship with hardcoded values
in the public repo.

Updating an existing install ([guide](https://docs.qhhoj.com/site/updating.md)):

```bash
git pull origin master
npm install && pip install -r requirements.txt
./manage.py migrate && ./manage.py check
./make_style.sh && ./manage.py collectstatic
./manage.py compilemessages && ./manage.py compilejsi18n
```
