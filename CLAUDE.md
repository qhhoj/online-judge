# CLAUDE.md

**QHHOJ — Mission Impossible** ([qhhoj.com](https://qhhoj.com)), the online judge of Trường THPT
Chuyên Quốc Học Huế. A Django site forked from [DMOJ](https://github.com/DMOJ/online-judge) via
[VNOJ](https://github.com/VNOI-Admin/OJ). Most of the code is upstream DMOJ; the interesting parts
are the fork deltas.

## Read the docs first

Before working in this repo, read the file in `docs/` that matches the task. Do not reconstruct this
from scratch — it took a full pass over the repo, CI, and `docs.qhhoj.com` to write.

| Task | Read |
|---|---|
| Understanding how the system runs — processes, submission flow, the bridge, events, Celery | [docs/architecture.md](docs/architecture.md) |
| Finding where code lives; what a directory or module is for | [docs/codebase-map.md](docs/codebase-map.md) |
| Anything touching models, migrations, contest scoring, or problem data | [docs/data-model.md](docs/data-model.md) |
| **Anything fork-specific**: virtual judge, problem mirroring, FSO contests, public ranking links, `VNOJ_*` settings | [docs/qhhoj-features.md](docs/qhhoj-features.md) |
| Setting up, running, testing, or linting | [docs/local-setup.md](docs/local-setup.md) |

External: [docs.qhhoj.com](https://docs.qhhoj.com) is the *deployment* guide (production install,
judge setup, contest formats, permission system, problem file format). It documents operations, not
the codebase.

## Rules that are easy to get wrong

- **Never edit `dmoj/settings.py`.** It `exec()`s `dmoj/local_settings.py` at the bottom; that
  gitignored file is where all overrides go.
- **Lint before finishing:** `flake8` from the repo root. Needs six plugins — `flake8`,
  `flake8-import-order`, `flake8-future-import`, `flake8-commas`, `flake8-logging-format`,
  `flake8-quotes`. Max line length 120, pycharm import order. `judge/migrations/` is excluded.
- **Tests:** `./manage.py test judge` (123 tests, 11 files). `judge/tests.py` is an empty stub —
  real tests live in `judge/models/tests/`, `judge/utils/tests/`, `judge/jinja2/markdown/`, and
  `judge/test_external_judge_async.py`. Reuse the helpers in `judge/models/tests/util.py`.
- **MySQL/MariaDB is required**, despite `settings.py` defaulting to SQLite. Raw SQL, `LOCK TABLES`,
  and `TRUNCATE TABLE` are used throughout.
- **Templates are Jinja2**, not Django templates. Filters live in `judge/jinja2/`.
- **Compiled assets are never committed.** `resources/style.css` and `/static` come from
  `./make_style.sh` + `collectstatic`.
- **`judge/middleware/` (singular) vs `judge/middlewares/` (plural)** both exist with near-identical
  user-activity modules. Only `judge.middlewares.user_activity_batch.BatchUserActivityMiddleware` is
  wired into `MIDDLEWARE`. Check before editing either.
- Config for `EXTERNAL_JUDGE_ENCRYPTION_KEY` and `USER_ACTIVITY_REALTIME_*` comes from **environment
  variables**, not settings.

## Environment status

This checkout is **not provisioned**: no venv, no `node_modules/`, no `dmoj/local_settings.py`, no
running MariaDB or Redis, and the `resources/libs` submodule is not checked out. There is also a
Python version blocker — the host has Python 3.14 only, while `Django>=5.1,<5.2` supports 3.10–3.13
and CI uses 3.11. See [docs/local-setup.md](docs/local-setup.md) before attempting to run anything.
