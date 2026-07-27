# QHHOJ-specific features

What this fork adds on top of upstream DMOJ and VNOJ. None of it is documented upstream, and most of
it is the subject of recent work — so this is the file to read before changing anything.

Two layers are mixed together in the codebase:

- **Inherited from VNOJ** — the `VNOJ_*` settings, organization system, contribution points, tagging.
  Present because QHHOJ forked VNOJ.
- **Added by QHHOJ** — virtual judge, problem mirroring, FSO contests, public ranking links, realtime
  activity tracking. Migrations `0214`–`0218`.

---

## Virtual judge / external OJ ("PCD") integration

*Migration `0217_external_judge`. The subject of the three most recent commits.*

Lets a problem delegate grading to a **remote online judge** over HTTP instead of to a local judge
server. Submissions on such a problem bypass the bridge entirely — see the "second judging path" note
in [architecture.md](architecture.md).

| Piece | File |
|---|---|
| Models | `judge/models/external_judge.py` |
| Submission client | `judge/external_judge.py` (~19 KB) |
| HTTP client | `judge/utils/external_judge_client.py` |
| Celery tasks | `judge/tasks/external_judge.py` |
| Admin | `judge/admin/external_judge.py` |
| UI | `judge/views/problem_data.py`, `templates/problem/data_virtual_judge.html` |
| Tests | `judge/test_external_judge_async.py` |

**Models**

- `ExternalJudgeConfig` — one remote API endpoint. Holds `base_url`, an
  **`encrypted_api_token`** (Fernet), `token_prefix`, `is_active`, and the polling knobs
  (`timeout_seconds`, `poll_timeout_seconds`, `poll_interval_seconds`, `max_poll_attempts`
  default 120).
- `ExternalProblem` — 1:1 with `Problem`. Binds it to a remote `oj` + `external_problem_id`, with
  `language_mappings` (local `Language` → remote language id) and a `metadata_cache`.
- `ExternalSubmission` — 1:1 with `Submission`. Tracks the remote run: `pcd_submission_id` (UUID),
  `pcd_system_status`, `pcd_status_canonical`, `pcd_vjudge_run_id`, `pcd_remote_url`,
  `pcd_runtime_ms`, `pcd_memory_kb`, `pcd_score_text`, `poll_attempts`, `raw_response`.

**Flow.** `submit_external_submission` (Celery, `max_retries=None`) posts the source to the remote
API and records the returned id; `poll_external_submission` then polls until a terminal status,
mapping the remote verdict onto QHHOJ's `SUBMISSION_RESULT` codes and writing them back onto the
local `Submission`.

**Settings**

```python
EXTERNAL_JUDGE_ENCRYPTION_KEY  # 32-byte URL-safe base64 Fernet key, read from env by default
EXTERNAL_JUDGE_ALLOW_HTTP      # defaults to DEBUG — plain HTTP endpoints only allowed in dev
```

`EXTERNAL_JUDGE_ENCRYPTION_KEY` is read from `os.environ` in `dmoj/settings.py`. Without it, API
tokens cannot be decrypted and the whole feature fails at runtime. Generate one with:

```bash
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

---

## Problem mirroring

*Migration `0216_problem_mirroring`.*

A problem can **mirror another problem's test data** rather than owning a copy. Useful for reusing a
problem across organizations without duplicating archives.

| Piece | File |
|---|---|
| Fields | `judge/models/problem.py` — `mirror_of`, `mirror_root` |
| Logic | `judge/utils/problem_mirror.py` |
| UI | `mirror-problem/` URLs and widget in `dmoj/urls.py`, `judge/views/problem_data.py` |
| Tests | `judge/models/tests/test_problem.py` |

**Two fields, not one.** `mirror_of` is the direct parent (`related_name='direct_mirrors'`);
`mirror_root` is the resolved ultimate source (`related_name='all_mirrors'`). `mirror_root` is
recomputed on save via `resolve_mirror_root_id()`, which is **cycle-safe** — it will not loop if
someone builds A→B→A. Anything that reads test data (`io_method`, archive paths) redirects through
`mirror_root` when `is_mirror` is true.

Key functions in `judge/utils/problem_mirror.py`:

| Function | Purpose |
|---|---|
| `validate_mirror_source_for_target()` | Authorization: may this user mirror this source into this target? |
| `get_mirrorable_source_queryset()` | The candidate list shown in the picker UI. |
| `resolve_mirror_root_id()` | Walk to the root, cycle-safe. |
| `rebuild_mirror_descendants()` | Fix up children after a relation changes. |
| `sync_mirror_archive_for_problem()` / `sync_mirror_archives_for_root()` | Propagate the actual data files. |

Visibility rules: only public problems, or private problems in an organization the user administers,
can be used as a mirror source. Change `validate_mirror_source_for_target()` carefully — it is the
only guard.

---

## Final Submission Only (FSO) contest format

*Migration `0215_add_final_submission_format`. Registered as `'final_submission'`.*

A contest format for offline/take-home rounds: contestants submit freely during the contest but
**nothing is judged until it ends**, and only the **last** submission per problem is scored.
Ranking is pure total score, IOI-style, with no time component.

```python
config_defaults = {
    'cumtime': False,     # always False — time is not part of scoring
    'auto_judge': True,   # False = require a manual trigger from the admin panel
}
```

`FinalSubmissionContestFormat` subclasses `DefaultContestFormat` (`judge/contest_format/final_submission.py`).

**Four independent triggers**, because "judge everything when the clock hits zero" needs to be
reliable:

| Mechanism | File | Role |
|---|---|---|
| In-process timers | `judge/utils/fso_scheduler.py` | `schedule_fso_contest_judging()` arms a `threading.Timer`; `reschedule_all_fso_contests()` re-arms everything on startup from `judge/apps.py:ready()`. |
| Celery beat | `judge/tasks/contest.py:check_final_submission_contests` | Runs every minute as a backstop. |
| Page view | `Contest.trigger_final_submission_judging()`, called from `judge/views/contests.py` | Fires when anyone loads an ended FSO contest page. |
| Manual | `judge/management/commands/check_fso_contests.py` | CLI trigger, with `--force` / `--rejudge-all`. |

**They are made safe by an atomic database claim, not by a cache.** `Contest.claim_fso_auto_judge()`
(`judge/models/contest.py`) does a single `UPDATE ... WHERE` against `Contest.fso_judged_end_time`,
so exactly one caller wins per `(contest, end_time)` — across processes, across restarts, with no
expiry. Storing the end time rather than a flag means extending a contest re-arms judging.

This matters because all four triggers are inherently duplicated: timers are armed per uwsgi worker,
beat can run on several workers, and the page-view trigger fires on every request. An earlier
implementation guarded them with a `LocMemCache` entry on a 24-hour TTL, which is per-process and
expires — the result was that every ended FSO contest was fully rejudged daily and once per worker,
each run deleting and regenerating the whole contest's test case results. See `plan.md` finding 1.

Automatic triggers pass `rejudge_all=False` and only pick up submissions in
`FSO_UNJUDGED_STATUSES` (`PD`, `IE`) — never finished ones. Only an explicit operator action (the
contest's Judge Submissions button, or `--rejudge-all`) resets everything.

Plus `_schedule_fso_rescore_with_debounce()` inside `judge/bridge/judge_handler.py`, which debounces
a contest rescore as the mass of queued submissions finishes grading.

`fix_fso_points.py` at the repo root is a one-off repair script for contests whose points went wrong.

---

## Contest public ranking links

*Migration `0218_contestpublicrankinglink`.*

Shareable, tokenised scoreboard URLs — so a scoreboard can be projected or sent to people without
accounts.

`ContestPublicRankingLink` (`judge/models/contest.py`) is 1:1 with `Contest`:

- `token` — 18 chars from `[A-Za-z0-9]`, generated with `secrets.choice`, unique and indexed.
- `status` — `public` or `private`.
- `expiry_mode` — `U` never expires, `M` minutes, `D` days, `A` absolute datetime — with
  `expiry_amount` / `expires_at`.
- `regenerated_at` — rotating the token invalidates old links.

Served at `/contest/<key>/public_ranking/` (see `dmoj/urls.py` and `judge/views/contests.py`), styled
by `resources/public-ranking.scss`, with a live countdown to contest end. Tests:
`judge/models/tests/test_public_ranking_link.py`.

---

## Realtime user-activity tracking

*Migration `0214_create_user_activity_models`.*

Tracks who is online and what they are doing, for admin monitoring.

| Piece | File |
|---|---|
| Models | `judge/models/user_activity.py` — `UserActivity`, `UserSession` |
| Middleware | `judge/middlewares/user_activity_batch.py:BatchUserActivityMiddleware` — the only one wired into `MIDDLEWARE` |
| Realtime store | `judge/utils/user_activity_realtime.py` (Redis) |
| Snapshot task | `judge/tasks/user_activity_realtime.py` (Celery beat) |
| Views | `judge/views/user_activity.py`, `user_activity_safe.py`; templates in `templates/user_activity/` |
| Admin pages | `admin/active-users/`, `admin/all-logs/` in `dmoj/urls.py` |
| CLI | `manage.py check_user_activity` |

Configured by `USER_ACTIVITY_REALTIME_*` environment variables, which set up a **separate Redis cache
alias** via `django_redis` alongside the default cache. Some views use raw SQL
(`judge/views/user_activity.py`).

> **Warning.** This feature has three near-duplicate implementations left in the tree — see the
> "Known warts" section of [codebase-map.md](codebase-map.md). Confirm which module is actually wired
> in before editing.

---

## Inherited VNOJ layer

Present because QHHOJ forked VNOJ; all gated by `VNOJ_*` settings near the top of `dmoj/settings.py`.

| Feature | Settings / files |
|---|---|
| **Organization performance points** | `VNOJ_ORG_PP_STEP`, `VNOJ_ORG_PP_ENTRIES`, `VNOJ_ORG_PP_SCALE` |
| **Contribution points (CP)** | `VNOJ_CP_COMMENT` (1/vote), `VNOJ_CP_TICKET` (10), `VNOJ_CP_PROBLEM` (20) |
| **Extended display ranks** | `VNOJ_DISPLAY_RANKS` — adds `setter`, `daor` ("Bedao Team"), `teacher` to DMOJ's set |
| **Interaction gates** | `VNOJ_INTERACT_MIN_PROBLEM_COUNT` (5 solves to comment/vote/edit profile), `VNOJ_BLOG_MIN_PROBLEM_COUNT` (10 to blog) |
| **Anti-cheat auto-ban** | `VNOJ_SHOULD_BAN_FOR_CHEATING_IN_CONTESTS`, `VNOJ_MAX_DISQUALIFICATIONS_BEFORE_BANNING` (3), `VNOJ_CONTEST_CHEATING_BAN_MESSAGE` |
| **Authoring limits** | `VNOJ_ORGANIZATION_ADMIN_LIMIT` (3), `VNOJ_PROBLEM_TIMELIMIT_LIMIT` (5s), `VNOJ_CONTEST_DURATION_LIMIT` (14d), `VNOJ_TESTCASE_HARD_LIMIT` (300) / `SOFT_LIMIT` (50) — each bypassed by a specific permission |
| **Community problem tagging** | `judge/models/tag.py`, `judge/views/tag.py`; gated by `VNOJ_TAG_PROBLEM_MIN_RATING` (1900) |
| **Org subdomain routing** | `VNOJ_IGNORED_ORGANIZATION_SUBDOMAINS`, `ContestMiddleware` in `judge/legacy_middleware.py` |
| **Problem import from other OJs** | `OJ_PROBLEM_PRESET` (regex → codename for Codeforces / AtCoder / Kattis / CF Gym / VNOJ), `OJ_LIST`, `judge/utils/codeforces_polygon.py`, `manage.py import_polygon_package` |
| **Discord notifications** | `DISCORD_WEBHOOK` dict, `VNOJ_DISCORD_WEBHOOK_THROTTLING`, `dmoj/throttle_discord_webhook.py`, `judge/tasks/webhook.py` |
| **IP-based auth** | `judge/ip_auth.py:IPBasedAuthBackend`, `IP_BASED_AUTHENTICATION_HEADER` |
| **Boring avatars** | `judge/boring_avatars/` — generated SVG default avatars (Gravatar still available) |
| **API v2** | `judge/views/api/api_v2.py`, gated by `VNOJ_ENABLE_API` (default `False`) |
| **Official contest mode** | `VNOJ_OFFICIAL_CONTEST_MODE` |

Permission semantics for most of this are documented at
[docs.qhhoj.com/site/permission_system.md](https://docs.qhhoj.com/site/permission_system.md) — the
permission system is unusually fine-grained (`edit_own_contest`, `edit_all_contest`,
`see_private_contest`, `clone_contest`, `contest_rating`, `create_mass_testcases`, …) and is the
mechanism by which the limits above are bypassed.

Also note `DATA_UPLOAD_MAX_NUMBER_FIELDS = 3000`, raised because the test-data editor posts several
fields per test case.

---

## Where features get gated

Almost everything above is a setting, not a code branch, and settings live in three places:

1. `dmoj/settings.py` — defaults, committed.
2. `dmoj/local_settings.py` — per-deployment overrides, **gitignored**, `exec()`'d at the bottom of
   `settings.py`.
3. Environment variables — only `EXTERNAL_JUDGE_ENCRYPTION_KEY` and the
   `USER_ACTIVITY_REALTIME_*` cache config are read from `os.environ`.

When a feature appears not to work, check which of the three is missing before reading code.
