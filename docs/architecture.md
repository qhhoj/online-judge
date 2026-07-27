# Architecture

How QHHOJ works at runtime. This is the part that is hard to reconstruct by reading files, because
the system is five cooperating processes, not one Django app.

> Not to be confused with `docs.qhhoj.com`, which is the *deployment* guide (a separate docsify site
> backed by [`github.com/qhhoj/docs`](https://github.com/qhhoj/docs)). This folder documents the
> *codebase*.

## Lineage

QHHOJ is a fork chain: [DMOJ](https://github.com/DMOJ/online-judge) → [VNOJ](https://github.com/VNOI-Admin/OJ)
→ QHHOJ. Most of what you read is upstream DMOJ; the `VNOJ_*` settings and the features in
[qhhoj-features.md](qhhoj-features.md) are the deltas. When something looks strange, checking upstream
DMOJ usually explains it.

## The five processes

```
                    browser
                       │
                  ┌────┴─────────────────────┐
                  │                          │
             ┌────▼────┐              ┌──────▼────────┐
             │  nginx  │              │  (ws / long-  │
             └────┬────┘              │   poll)       │
                  │                   └──────┬────────┘
          uwsgi   │                          │
        ┌─────────▼──────────┐      ┌────────▼─────────────┐
        │  SITE              │      │  EVENT SERVER        │
        │  Django            │─────▶│  websocket/daemon.js │
        │  dmoj.wsgi         │ post │  (Node)              │
        └───┬───────────┬────┘      └──────────────────────┘
            │           │                       ▲
   TCP 9998 │           │ Redis                 │ post
            │           │                       │
    ┌───────▼───────┐  ┌▼──────────────┐  ┌─────┴─────────┐
    │  BRIDGED      │  │ CELERY WORKER │  │               │
    │ judge.bridge  │  │ dmoj_celery   │  │               │
    │ .daemon       │  └───────────────┘  │               │
    └───────┬───────┘                     │               │
   TCP 9999 │                             │               │
    ┌───────▼──────────────────────────────┴──────┐
    │  JUDGE SERVER(S)  — separate repo, Docker   │
    │  vnoj/judge-tiervnoj                        │
    └─────────────────────────────────────────────┘
                          │
                  MariaDB / MySQL  ◀── all of the above
```

| Process | Entry point | Purpose |
|---|---|---|
| **site** | `dmoj/wsgi.py` (or `manage.py runserver` in dev) | The Django web application. Everything a user sees. |
| **bridged** | `dmoj_bridge_async.py` or `manage.py runbridged` | Long-lived TCP daemon brokering between the site and judge servers. |
| **judge server** | *not in this repo* | Actually compiles and runs submissions in a sandbox. Connects *out* to bridged. |
| **celery worker** | `dmoj_celery.py` | Background jobs: rescoring, exports, external-judge polling, scheduled tasks. Redis is the broker. |
| **event server** | `websocket/daemon.js` (Node) | Pub/sub fan-out so browsers get live submission and contest updates. Optional. |

Only **site** is needed to browse the codebase's output. Judging requires site + bridged + a judge
server. Live status updates require the event server. Background jobs require Celery + Redis.

## Submission flow, end to end

This is the single most important path in the codebase.

1. **User submits.** `judge/views/problem.py` (`ProblemSubmit`) validates and creates a `Submission`
   row with `status='QU'` plus a `SubmissionSource`.
2. **Site pokes the bridge.** `judge/judgeapi.py:judge_submission()` opens a short-lived TCP
   connection to `BRIDGED_DJANGO_ADDRESS` (default `localhost:9998`) and sends a
   `submission-request` packet.
3. **Bridge receives it.** `judge/bridge/django_handler.py:DjangoHandler` decodes the packet and
   calls into `judge/bridge/judge_list.py:JudgeList`, the in-memory registry of connected judges.
4. **Bridge dispatches.** `JudgeList` picks an online judge that supports the problem and language
   (respecting `judge_priority.py`), and hands the job to that judge's
   `judge/bridge/judge_handler.py:JudgeHandler`.
5. **Judge grades.** The judge server streams packets back: `grading-begin`, `compile-error` /
   `compile-message`, `batch-begin` / `batch-end`, one `test-case-status` per case, then
   `grading-end`.
6. **Bridge persists.** `JudgeHandler` writes `Submission.status`/`result`/`points`/`time`/`memory`
   and one `SubmissionTestCase` row per case, and recomputes contest scores where relevant.
7. **Bridge publishes.** Each state change is posted through `judge/event_poster.py` to the event
   server, which fans it out to any browser subscribed to that submission's channel — this is why a
   submission page updates without reloading.

Aborts and rejudges run the same route in reverse: `judgeapi.py` sends `terminate-submission`,
`disconnect-judge`, or `disable-judge`.

### Wire protocol

Both bridge channels speak the same thing, defined in `judge/bridge/base_handler.py`:

- `ZlibPacketHandler` — a **length-prefixed, zlib-compressed JSON** packet over a raw TCP socket.
- Two independent listeners, started together by `judge/bridge/daemon.py:judge_daemon()`:
  - `BRIDGED_JUDGE_ADDRESS` (default `:9999`) — judge servers connect **in**. Authenticated by the
    judge's `name` + `auth_key`, which you create in Django admin.
  - `BRIDGED_DJANGO_ADDRESS` (default `:9998`) — the Django process connects in. **Must not be
    reachable from the internet**; it is unauthenticated.
- `BRIDGED_JUDGE_PROXIES` enables PROXY-protocol parsing when judges arrive via a load balancer.

On startup `judge_daemon()` marks every `Judge` offline and flips any submission stuck in
`IN_PROGRESS_GRADING_STATUS` (`QU`, `P`, `G`) to `IE`, so a bridge restart never leaves ghosts.

### The second judging path: virtual judge

There is a **completely separate** grading route that never touches the bridge. If a problem has an
`ExternalProblem` attached, the submission is forwarded to a remote online judge over HTTP and its
verdict is polled back by a Celery task. See [qhhoj-features.md](qhhoj-features.md#virtual-judge--external-oj-pcd-integration).
Code: `judge/external_judge.py`, `judge/utils/external_judge_client.py`, `judge/tasks/external_judge.py`.

## Event server

`websocket/daemon.js` is a small standalone Node process (ESM, `"type": "module"`). It runs three
listeners:

| Listener | Config key | Who connects |
|---|---|---|
| Subscriber WebSocket | `get_host` / `get_port` | Browsers. Send `set_filter` to pick channels, then receive pushes. |
| Publisher WebSocket | `post_host` / `post_port` | The Django site and bridge, via `judge/event_poster_ws.py`. |
| HTTP long-poll | `http_host` / `http_port` | Browsers without WebSocket, at `/channels/<a>|<b>?last=<id>`. |

Messages are kept in an in-memory ring buffer (`websocket/queue.js`, `max_queue` default 50) so a
client that reconnects can catch up. Nothing is persisted.

Its config file `websocket/config.js` is **gitignored** and must be written by hand — see
[local-setup.md](local-setup.md). The ports there must line up with Django's `EVENT_DAEMON_POST`,
`EVENT_DAEMON_GET`, and `EVENT_DAEMON_POLL`.

`judge/event_poster.py` picks a backend at import time:

- `EVENT_DAEMON_USE = False` → every post is a no-op. This is the default, and is fine for development.
- `EVENT_DAEMON_AMQP` set → `judge/event_poster_amqp.py`, talking to RabbitMQ instead.
- otherwise → `judge/event_poster_ws.py`, talking to `websocket/daemon.js`.

## Celery

`dmoj/celery.py` builds the app from Django settings under the `CELERY` namespace, autodiscovers
`judge/tasks/*.py`, and defines a **beat schedule** with two periodic jobs:

| Job | Interval | Task |
|---|---|---|
| `check-final-submission-contests` | every minute | `judge.tasks.contest.check_final_submission_contests` |
| `refresh-user-activity-realtime-snapshot` | `USER_ACTIVITY_REALTIME_SNAPSHOT_INTERVAL_SECONDS` | `judge.tasks.user_activity_realtime.refresh_user_activity_realtime_snapshot` |

Both are QHHOJ additions. Note that a beat process must actually be running for these to fire; the
FSO format additionally arms in-process `threading.Timer`s as a belt-and-braces mechanism (see
`judge/utils/fso_scheduler.py`, invoked from `judge/apps.py:ready()`).

Task-status polling for long jobs is exposed to the frontend by `judge/views/tasks.py` under
`/tasks/status/<task_id>`.

## Templates and rendering

The primary template engine is **Jinja2** via `django_jinja`, not Django templates. Filters and
globals live in `judge/jinja2/` and are registered through `judge/jinja2/registry.py`; context
processors are in `judge/template_context.py`. `judge/templatetags/` exists for the small remaining
Django-template surface (mostly admin).

Markdown goes through `judge/jinja2/markdown/` with per-content-type sanitisation policies defined by
`MARKDOWN_STYLES` in `dmoj/settings.py` — a problem statement is allowed more HTML than a comment.
Optional rendering microservices are pluggable: `judge/utils/mathoid.py` (math), `texoid.py`
(TikZ diagrams), `pdfoid.py` (PDF statements), `camo.py` (image proxying).

## Settings that wire the seams

Everything above is glued together by settings, all overridable in `dmoj/local_settings.py`:

| Concern | Settings |
|---|---|
| Bridge | `BRIDGED_JUDGE_ADDRESS`, `BRIDGED_JUDGE_PROXIES`, `BRIDGED_DJANGO_ADDRESS`, `BRIDGED_DJANGO_CONNECT` |
| Event server | `EVENT_DAEMON_USE`, `EVENT_DAEMON_POST`, `EVENT_DAEMON_GET`, `EVENT_DAEMON_POLL`, `EVENT_DAEMON_KEY`, `EVENT_DAEMON_AMQP*` |
| Celery | `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` |
| Problem data | `DMOJ_PROBLEM_DATA_ROOT` — the directory the judge servers also mount |
| Virtual judge | `EXTERNAL_JUDGE_ENCRYPTION_KEY`, `EXTERNAL_JUDGE_ALLOW_HTTP` |

Two of these have insecure defaults in `dmoj/settings.py` and **must** be overridden in production:
`EVENT_DAEMON_SUBMISSION_KEY` and `EVENT_DAEMON_CONTEST_KEY` are hardcoded literals in the repo, as
is `SECRET_KEY`.

## Deployment shape

Not represented in this repo at all — there is no Dockerfile, compose file, nginx config, or
supervisor config here. Production runs uwsgi + nginx with supervisord keeping `site`, `bridged`,
`celery`, and `wsevent` alive. Sample configs live in
[`qhhoj/docs/sample_files`](https://github.com/qhhoj/docs/tree/master/sample_files): `uwsgi.ini`,
`nginx.conf`, `site.conf`, `bridged.conf`, `celery.conf`, `wsevent.conf`, `local_settings.py`.

`dmoj/wsgi_async.py` is a gevent-monkeypatched variant of the WSGI entry point for greenlet-based
serving. There is no `asgi.py` — the project is WSGI-only; "async" here always means gevent.
