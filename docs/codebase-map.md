# Codebase map

Where things live. Read [architecture.md](architecture.md) first if you want to know *why* they live
there.

## Top level

| Path | What it is |
|---|---|
| `dmoj/` | The Django *project*: settings, root URLconf, WSGI/Celery entry points. Very little logic. |
| `judge/` | The Django *app*. Essentially the entire product is in here — one app, ~140 migrations. |
| `templates/` | Jinja2 templates (plus a few Django templates), organised by feature. |
| `resources/` | Static asset *sources*: SCSS, JS, fonts, icons. Compiled output is gitignored. |
| `websocket/` | The Node event server. Independent of Python. |
| `django_ace/` | Vendored Django app wrapping the Ace code editor widget. |
| `locale/` | i18n catalogues — `en/` and `vi/`. |
| `scripts/` | One helper, `check-package-installed.js`. |

Root files worth knowing:

| File | Purpose |
|---|---|
| `manage.py` | Standard Django entry point (imports `dmoj/compressor_patch.py` first). |
| `dmoj_celery.py` | Celery worker entry point — `celery -A dmoj_celery worker`. |
| `dmoj_bridge_async.py` | gevent-patched launcher for the bridge daemon. |
| `make_style.sh` | Compiles SCSS → CSS for both light and dark themes. |
| `.ci.settings.py` | The `local_settings.py` CI uses. The reference for a working test config. |
| `.flake8` | Lint config. Excludes `judge/migrations/`, `local_settings.py`, `fc_*`. |
| `fix_fso_points.py` | One-off maintenance script for the FSO contest format. |
| `dmoj_install_pymysql.py` | Installs `pymysql` as a `MySQLdb` shim when the C driver is unavailable. |

## `dmoj/` — project config

### `settings.py`

One long file, ~820 lines, read top to bottom. Rough sections in order:

1. Core Django + site identity (`SECRET_KEY`, `DEBUG`, `SITE_NAME`, `DMOJ_SSL`, 2FA flags).
2. DMOJ point system (`DMOJ_PP_STEP`, `DMOJ_PP_ENTRIES`, `DMOJ_PP_BONUS_FUNCTION`).
3. **`VNOJ_*` / QHHOJ block** (~lines 55–200) — most fork-specific behaviour is toggled here. See
   [qhhoj-features.md](qhhoj-features.md).
4. External-OJ import presets (`OJ_PROBLEM_PRESET`, `OJ_LIST`), Discord webhooks.
5. CDN URLs, problem limits, submission/rating/rate-limit knobs, data-download settings.
6. PDF rendering, theme, Martor editor, `MARKDOWN_STYLES` sanitisation policies, upload dirs.
7. `INSTALLED_APPS` / `MIDDLEWARE` / `TEMPLATES` / `DATABASES` / `CACHES` / auth backends.
8. Bridge and event-server addresses.
9. **At the very bottom**: `exec()` of `dmoj/local_settings.py` if it exists.

> **Convention: never edit `settings.py`.** Put overrides in `dmoj/local_settings.py`, which is
> gitignored and loaded last. This keeps `git pull` clean.

`INSTALLED_APPS` starts as `()` and is appended to, because `wpadmin` is added conditionally
depending on whether it imports — so grepping for a single `INSTALLED_APPS = [...]` block will
mislead you.

### Other files in `dmoj/`

| File | Purpose |
|---|---|
| `urls.py` | Root URLconf, ~737 lines. See the route-group table below. |
| `celery.py` | Celery app + beat schedule. |
| `wsgi.py` / `wsgi_async.py` | Sync and gevent WSGI entry points. No `asgi.py` exists. |
| `compressor_patch.py` | django-compressor compatibility shim for Django 5. |
| `email.py`, `throttle_mail.py`, `throttle_discord_webhook.py` | Outbound-notification throttling. |

`urls.py` route groups, roughly in file order: auth/registration/2FA/API tokens → custom admin log
pages → Django admin → social auth → home → `problem/` (view, edit, editorial, pdf, clone, submit,
rank, test_data, mirror-problem, import-polygon, suggest) → `submissions/` → `user/` → `comments/` →
`contests/` (incl. `public_ranking`, `official_ranking`, moss, clone, data export) → `organizations/`
→ `runtimes/`, `status/`, `posts/` → admin AJAX + select2 + martor preview endpoints → feeds →
`stats/`, `tag/`, `tasks/` → `sitemap.xml` → `widgets/` → `URL/` shortener → `api/v2/`.

## `judge/` — the app

### Subpackages

| Path | Responsibility |
|---|---|
| `models/` | All ORM models. See [data-model.md](data-model.md). |
| `views/` | Request handlers, one module per feature area. |
| `admin/` | Django admin customisations, one module per model family. |
| `bridge/` | The judge-server TCP daemon. See [architecture.md](architecture.md). |
| `migrations/` | 142 numbered migrations. Excluded from flake8. |
| `jinja2/` | Jinja2 filters/globals + the markdown pipeline. Registered via `registry.py`. |
| `templatetags/` | Django-template tags (small surface — most templates are Jinja2). |
| `widgets/` | Form widgets: `select2.py`, `martor.py`, `checkbox.py`, `mixins.py`. |
| `tasks/` | Celery tasks. |
| `utils/` | Grab-bag of helpers — see below. |
| `contest_format/` | Pluggable contest scoring strategies. |
| `management/commands/` | CLI commands. |
| `boring_avatars/` | SVG default-avatar generator. |
| `fixtures/` | Seed data: `navbar`, `language_small`/`_more`/`_all`, `demo`. |

### The big view modules

`judge/views/` has a heavy tail. If you are looking for feature logic, it is almost certainly in one
of these three:

- `contests.py` (~74 KB) — contest list/detail, join/leave, rankings, public ranking, MOSS, clone,
  announcements, data download.
- `problem.py` (~54 KB) — problem list/detail, random, submit, clone, suggest, Polygon import.
- `problem_data.py` (~40 KB) — the test-data editor, checker config, and the virtual-judge /
  mirror configuration forms.

Others: `organization.py`, `submission.py`, `user.py`, `blog.py`, `comment.py`, `ticket.py`,
`status.py`, `stats.py`, `select2.py` (autocomplete endpoints), `widgets.py` (martor preview and
image upload), `tasks.py` (Celery status polling), `register.py`, `two_factor.py`, `tag.py`,
`language.py`, `license.py`, `magazine.py`, `mailgun.py` (inbound mail webhook), `URL.py`
(shortener), `error.py`, `flatpages.py`, `preview.py`, `ranked_submission.py`, `problem_manage.py`,
`user_activity.py` / `user_activity_safe.py`, and `api/api_v2.py`.

### Standalone modules in `judge/`

| Module | Purpose |
|---|---|
| `judgeapi.py` | Django-side client for the bridge. Submit, abort, disable judge. |
| `event_poster.py` + `_ws.py` / `_amqp.py` | Pluggable live-event publishing. |
| `external_judge.py` | Virtual-judge submission client (~19 KB). |
| `apps.py` | `JudgeAppConfig.ready()` — backfills missing `Profile`s, arms FSO timers, applies a `force_text` shim. |
| `legacy_middleware.py` | `ShortCircuit`, `API`, `MiscConfig`, `DMOJLogin`, `DMOJImpersonation`, `Contest` middleware. Note the file is `judge/middleware.py` on disk. |
| `ratings.py` | Contest rating calculation. |
| `performance_points.py` | The points/pp system (raw SQL). |
| `dblock.py` | MySQL `LOCK TABLES` mutex. **Not portable to SQLite.** |
| `ip_auth.py` | IP-based authentication backend (non-standard; in `AUTHENTICATION_BACKENDS`). |
| `social_auth.py` | Custom python-social-auth pipeline steps. |
| `signals.py` | `post_save` / `pre_delete` cache-invalidation hooks. |
| `template_context.py` | Jinja2 context processors. |
| `fulltext.py`, `feed.py`, `sitemap.py`, `highlight_code.py`, `lxml_tree.py`, `comments.py`, `timezone.py`, `user_log.py`, `caching.py`, `judge_priority.py` | Supporting infrastructure. |

### `judge/utils/` highlights

`codeforces_polygon.py` (~36 KB, Polygon package import), `problem_mirror.py`,
`external_judge_client.py`, `fso_scheduler.py`, `user_activity_realtime.py`, `problem_data.py`,
`problems.py`, `raw_sql.py` (custom `RawSQLJoin`), `diggpaginator.py`, `infinite_paginator.py`,
`mathoid.py` / `texoid.py` / `pdfoid.py` / `camo.py` (rendering microservice clients), `pwned.py`
(HaveIBeenPwned password validator), `two_factor.py`, `tickets.py`, `stats.py`, `cms.py`,
`judge_api.py`.

### Management commands

Run as `./manage.py <name>`.

| Command | Purpose |
|---|---|
| `runbridged` | Run the judge bridge daemon. |
| `adduser` | Create a user (`--superuser`, `--staff`). Also creates the `Profile`. |
| `batchadduser` | Bulk user creation. |
| `addjudge` | Create a judge record. |
| `create_problem` | Create an empty problem. |
| `import_polygon_package` | Import a Codeforces Polygon full package. |
| `submit_polygon_solutions` | Submit the solutions bundled in a Polygon package. |
| `copy_language` | Let problems allowing `<source>` also accept `<target>`. |
| `update_permissions` | Reload permissions for given apps (or all). |
| `runmoss` | Run MOSS plagiarism detection. |
| `render_pdf` | Render a problem statement to PDF. |
| `generate_sitemap` | Write a sitemap to a directory. |
| `generate_api_token` | Generate/regenerate a user's 48-char API token. |
| `export_event_feed` | Export a CLICS XML event feed (ICPC Resolver etc.). |
| `export_contest_submissions` / `_details` | Export contest submissions. |
| `problem_points_scaling` | Rescale problem points from 0.0–2.0 to 800–3500. |
| `move_user_content` | Move comments and submissions between users. |
| `check_fso_contests` | Find ended FSO contests and trigger judging. |
| `check_user_activity` | Report activity-tracking status. |
| `camo` | Print the camo URL for a given URL. |
| `makedmojmessages` | Create/update i18n message files. |

## `templates/`

Organised by feature, mirroring `judge/views/`: `problem/`, `contest/`, `organization/`, `user/`,
`submission/`, `ticket/`, `blog/`, `comments/`, `stats/`, `status/`, `admin/`, `widgets/`, `tag/`,
`registration/`, `flatpages/`, `shortener/`, `newsletter/`, `timezone/`, `user_activity/`, plus
root-level `base.html`, `home.html`, and one-off event pages.

## `resources/` and the asset pipeline

Sources are `.scss` and `.js`. The build is:

```
resources/*.scss  ──▶  make_style.sh  ──▶  resources/style.css
                       (sass + postcss/         resources/dark/style.css
                        autoprefixer,           resources/martor-description.css
                        two theme passes)       resources/select2-dmoj.css
                              │
                              ▼
                    ./manage.py collectstatic  ──▶  STATIC_ROOT
```

`make_style.sh` copies `vars-default.scss` or `vars-dark.scss` over `vars.scss` and runs the pass
twice, which is why `resources/vars.scss` is gitignored — it is a build artefact.

**Nothing compiled is committed.** `.gitignore` excludes `resources/style.css`, `resources/dark`,
`resources/vars.scss`, `resources/martor-description.css`, `resources/select2-dmoj.css`,
`sass_processed/`, `/static`, and `node_modules/`. If the site renders unstyled, you have not run
`make_style.sh`.

`resources/libs/` is a **git submodule** pointing at `github.com/qhhoj/site-assets`. It is currently
**not checked out** in this working copy — run `git submodule update --init --recursive`.

`resources/caniuse.json` is refreshed by a weekly CI job (upstream DMOJ only).

## `websocket/`

Three files: `daemon.js` (the server), `queue.js` (linked-list ring buffer), `types.d.ts`.
`config.js` is gitignored and must be created by hand. `package.json` defines no `start` script —
launch it as `node websocket/daemon.js`. The npm `format` / `format:check` scripts run Prettier over
this directory only.

## Known warts

Worth knowing before you go looking for the "right" implementation:

- **Three user-activity implementations coexist.** `judge/middleware/user_activity.py`,
  `judge/middlewares/{user_activity,user_activity_batch,user_activity_safe}.py`, and
  `judge/views/{user_activity,user_activity_safe}.py`. Only
  `judge.middlewares.user_activity_batch.BatchUserActivityMiddleware` is wired into `MIDDLEWARE`.
  The near-identical `middleware/` (singular) and `middlewares/` (plural) directories are an easy
  trap. Treat the unwired modules as dead code until proven otherwise.
- **`judge/middleware.py` is imported as `judge.legacy_middleware`** — the module name in
  `MIDDLEWARE` does not match the filename.
- `judge/tests.py` is an empty stub; the real tests are elsewhere (see [local-setup.md](local-setup.md)).
- `settings.py` ships hardcoded `SECRET_KEY`, `EVENT_DAEMON_SUBMISSION_KEY`, and
  `EVENT_DAEMON_CONTEST_KEY` values that are in the public repo.
