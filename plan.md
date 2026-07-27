# QHHOJ — Audit and Action Plan

Findings from a full pass over the codebase covering **bugs, security issues, ambiguity, and future
work**, ordered most important first.

**Method.** Three parallel audits (security, correctness/races, technical debt), with every P0 and P1
finding independently re-verified by reading the code — agent claims were not taken at face value.
Several reported issues were checked and turned out to be non-issues; they are listed at the end so
nobody re-investigates them.

**Nothing was executed against a running system.** Severity for findings 1, 8 and 10 depends on how
the site is actually deployed; those are stated conditionally, with the command that resolves the
condition. See the [FSO runbook](#diagnosing-the-fso-issue-on-the-live-server) at the end.

Background reading: [`docs/architecture.md`](docs/architecture.md),
[`docs/qhhoj-features.md`](docs/qhhoj-features.md), [`docs/codebase-map.md`](docs/codebase-map.md).

---

## P0 — Critical

### 1. Every ended FSO contest is fully rejudged every 24 hours, forever — ✅ FIXED

> **Status: fixed.** The cache guard was replaced with an atomic database claim
> (`Contest.fso_judged_end_time`, migration `0219`), the automatic path no longer resets finished
> submissions, and 19 regression tests were added in `judge/models/tests/test_fso.py`. The
> description below is kept as the record of what was wrong. **The migration must still be applied
> on the server** — until then, nothing changes in production.
>
> One extra trigger was found during the fix that is not in the original list: a **fifth** call site,
> `trigger_final_submission_judging()`, runs on *every page view* of an ended FSO contest
> (`judge/views/contests.py:422` and `:1149`). With a per-process cache that was likely the dominant
> trigger — each uwsgi worker had its own guard, so refreshing the scoreboard round-robined across
> workers and re-fired judging.

| | |
|---|---|
| **Where** | `judge/tasks/contest.py:355-410` and `:224-282`; `judge/utils/fso_scheduler.py:70-118`; `judge/management/commands/check_fso_contests.py:44-59`; `judge/models/contest.py:695-711` |
| **Effort** | ~half a day, plus a migration |

Three things combine into a runaway loop.

**The query has no lower bound.** `check_final_submission_contests`, wired to Celery beat every
minute (`dmoj/celery.py:25-29`), selects:

```python
Contest.objects.filter(format_name='final_submission', end_time__lte=now)
```

That is *every FSO contest that has ever ended* — the set only grows.

**The dedup guard is process-local and expires.** Re-triggering is gated by
`cache.get`/`cache.set` on `f'fso_judged_{contest.id}_{end_time_ts}'` with an **86400-second TTL**.
The `default` cache is `LocMemCache` (`dmoj/settings.py:737-745`), which is per-process and does not
survive a restart.

**The guarded action is not idempotent.** `_judge_final_submissions_impl` selects all submissions
except `P`/`G` — *including already-completed `D` ones* — then:

```python
SubmissionTestCase.objects.filter(submission_id__in=submission_ids).delete()
submissions.update(status='QU', result=None, points=None, time=None, memory=None, ...)
```

and redispatches every one to the judge queue.

**What actually happens.** The cache key expires after 24 h, the next beat tick misses, and the
contest is mass-rejudged again — deleting and regenerating all its test-case results. Judge load
grows linearly with the number of FSO contests ever run. Any worker restart (deploy, OOM,
`--max-tasks-per-child`, autoscale) resets the cache and triggers it immediately. With multiple
worker processes, several can pass the `cache.get` check before any calls `cache.set`.

The existence of `fix_fso_points.py` at the repo root is consistent with this having already caused
damage.

**Fix**

- Persist the trigger marker in the database — a `Contest.fso_judged_for_end_time` column — instead
  of a process-local cache. This survives restarts and is shared across processes.
- Where a cache is still used, gate with `cache.add()` (atomic set-if-absent), never `get` then
  `set`.
- Make `_judge_final_submissions_impl` idempotent: skip submissions already judged for the *current*
  `end_time` rather than blindly re-including `D`.
- Bound the beat query with a lookback window (e.g. `end_time__gte=now - timedelta(days=1)`) as a
  belt-and-braces measure.

All three trigger paths (`fso_scheduler`, beat task, management command) share the same broken
scheme and must be fixed together.

### 2. Django admin bypasses mirror authorization

| | |
|---|---|
| **Where** | `judge/admin/problem.py:34-66`; `judge/models/problem.py:333-341`, `:737-748` |
| **Effort** | ~1 hour |

`validate_mirror_source_for_target` (`judge/utils/problem_mirror.py:27`) enforces "only public
problems, or private problems in an org you administer, may be mirrored". It is called from exactly
two places: `judge/forms.py:349` and `judge/views/problem_data.py:361` — both site-facing.

The **admin** path calls it nowhere:

- `ProblemForm` (`judge/admin/problem.py:34-66`) defines no `clean()`.
- `mirror_of` has no `limit_choices_to`, and `ProblemAdmin` sets no `formfield_for_foreignkey`, so
  the `ModelChoiceField` validates submitted PKs against `Problem.objects.all()`.
- The select2 widget points at `problem_select2` (`judge/views/select2.py:143`, scoped to visible
  problems) rather than `mirror_problem_select2` (`:149`, which uses
  `get_mirrorable_source_queryset`) — but a widget is a **UI filter only** and does not constrain
  what a POST may contain.
- `Problem.save()` (`:737-748`) computes `mirror_root_id` with no authorization check at all.

**Exploit.** A user with `edit_own_problem` on a problem they author — an ordinary problem-setter
role, not superuser — opens `/admin/judge/problem/<their_id>/change/` and POSTs
`mirror_of=<any problem PK>`. Problem IDs are sequential integers, so hidden or unreleased contest
problems are trivially enumerable. Their own problem now grades against the target's test data,
giving them a pass/fail oracle over an unreleased problem.

The read path is fine — `_can_download_problem_data` (`judge/views/problem_data.py:86-92`) correctly
checks `mirror_root.is_editable_by`. Only the write path is unguarded.

**Fix.** Add `clean()` to the admin `ProblemForm` calling `validate_mirror_source_for_target`;
restrict the queryset via `formfield_for_foreignkey`; and enforce in `Problem.save()` as defence in
depth so no future write path can bypass it.

---

## P1 — High

### 3. `delete_user_logs` is a GET-triggered destructive action

`judge/views/user_activity.py:361-373` deletes every `UserActivity` and `UserSession` row for a user
with **no `request.method` check**. `delete_anonymous_logs` immediately below (`:376-392`) *does*
check `if request.method == 'POST'` — so this is an oversight, not a design choice.

It is rendered as a plain `<a href="...">` in three templates
(`templates/user_activity/user_detail.html:891`,
`templates/admin/user_activity/user_detail.html:483`,
`templates/admin/user_activity/user_detail_standalone.html:836`). GET bypasses CSRF middleware
entirely, so any link or image auto-loaded in a logged-in staff member's browser silently wipes that
user's audit trail.

**Fix.** `@require_POST` and convert the template links to POST forms with `{% csrf_token %}`.
*Effort: ~30 min.*

### 4. Aborting a virtual-judge submission is silently reversed later

`judge/judgeapi.py:190-203` (`abort_submission`) has no `has_external_problem` branch — unlike
`judge_submission` (`:141-143`) and the admin reject path (`judge/views/widgets.py:60-62`), both of
which do special-case external problems. The asymmetry is the bug.

For a submission routed to the external judge (never sent to the bridge at all):

1. The bridge finds nothing to abort and returns `judge-aborted: False`.
2. `abort_submission` treats that as confirmation and sets `status='AB'`.
3. `ExternalSubmission.pcd_system_status` is untouched, so `poll_external_submission`'s early-return
   guard (`judge/external_judge.py:92`, which requires *both* a terminal submission status *and* a
   terminal `pcd_system_status`) does not fire — polling continues.
4. `finalize_external_submission` (`:448-528`) later does
   `Submission.objects.filter(...).update(status=..., result=...)`, **overwriting the abort** with
   the real verdict.

Separately, the `judge_request` call here is not wrapped in try/except (unlike `judge_submission`),
so aborting *any* submission while the bridge is down raises through the view
(`judge/views/submission.py:404-412`) as a 500.

**Fix.** Branch to `reject_external_submission` for external submissions — it sets
`pcd_system_status='rejected'`, which the poller does honour. Wrap the bridge call.
*Effort: ~1 hour.*

### 5. Deleting a mirror root leaves descendants inconsistent

`mirror_of` and `mirror_root` are both `on_delete=SET_NULL`
(`judge/models/problem.py:333-350`). Django executes that cascade as a **bulk UPDATE**, bypassing
`Problem.save()` and therefore `rebuild_mirror_descendants`. There is no `post_delete` receiver for
`Problem` anywhere in `judge/signals.py`.

Chain `R ← M1 (mirror_of=R) ← M2 (mirror_of=M1, mirror_root=R)`. Delete `R`:

- `M1.mirror_of` and `M1.mirror_root` both null — consistent by luck.
- `M2.mirror_root` is nulled (it pointed at `R`), but **`M2.mirror_of` still points at `M1`**.

`M2` now has `is_mirror == True` with `mirror_root_id == None`, so `io_method` (`:706-709`) falls
through to `M2`'s own — empty — test data. No exception; it just silently serves nothing.

**Fix.** Add a `pre_delete`/`post_delete` receiver that re-points affected mirrors via
`rebuild_mirror_descendants`. *Effort: ~2 hours including a test.*

### 6. Six dependencies float on branch HEAD

`requirements.txt:22-27`:

```
dmoj-wpadmin          @ git+https://github.com/qhhoj/dmoj-wpadmin.git
django-fernet-fields  @ git+https://github.com/qhhoj/django-fernet-fields.git
jsonfield             @ git+https://github.com/qhhoj/jsonfield.git
ansi2html             @ git+https://github.com/qhhoj/ansi2html.git
martor                @ git+https://github.com/qhhoj/martor.git
markdown2             @ git+https://github.com/qhhoj/python-markdown2.git
```

No `@tag`, no `@<sha>`. pip resolves each to whatever is HEAD of the fork's default branch *at
install time*. Two builds a week apart can differ with no change to `requirements.txt`, and a
compromise of any of those six repos lands directly in production on the next deploy. There is no
Python lockfile — `package-lock.json` covers npm only.

**Fix.** Pin each to a commit SHA. Consider `pip-compile` for a full lockfile. *Effort: ~1 hour.*

### 7. Django 5.1 is past end of life

`requirements.txt:2` pins `Django>=5.1,<5.2`. Django 5.2 is the LTS; 5.1's support window has
elapsed, so the site is running an unpatched Django.

The likely blocker is `django_compressor`, which needed `dmoj/compressor_patch.py` for 5.1 — worth
checking whether that is still required on 5.2. This upgrade also resolves the Python 3.14 problem
blocking local development (see [`docs/local-setup.md`](docs/local-setup.md)).

*Effort: 1–3 days, needs real testing.*

### 8. Committed secrets — verify and rotate

`dmoj/settings.py:26` (`SECRET_KEY`), `:678-679` (`EVENT_DAEMON_SUBMISSION_KEY`,
`EVENT_DAEMON_CONTEST_KEY`) are hardcoded literals in a public repo.

This is upstream DMOJ's placeholder pattern and is *fine if* `dmoj/local_settings.py` overrides them.
But `SECRET_KEY` signs session cookies and password-reset tokens — if production is running the
committed value, anyone can forge an admin session.

```bash
grep -E "SECRET_KEY|EVENT_DAEMON_(SUBMISSION|CONTEST)_KEY" dmoj/local_settings.py
```

If any is absent, rotate it. Note that rotating `SECRET_KEY` invalidates all sessions and pending
password-reset links.

For contrast, `EXTERNAL_JUDGE_ENCRYPTION_KEY` is handled correctly — read from the environment, with
`ImproperlyConfigured` raised when missing and no insecure fallback. That is the pattern to copy.

---

## P2 — Medium

### 9. zlib decompression bomb in the bridge protocol
`judge/bridge/base_handler.py:134`. `MAX_ALLOWED_PACKET_SIZE` (`:20`) caps the **compressed** payload
at 8 MB, but `zlib.decompress(data)` output is unbounded — and this runs on the first packet, before
the judge handshake is validated. An 8 MB crafted payload can expand to gigabytes and exhaust the
bridge process. *Fix:* `zlib.decompressobj().decompress(data, max_length=N)`, disconnect if exceeded.

### 10. The bridge's Django channel is unauthenticated
`judge/bridge/django_handler.py:17-66` has no equivalent of `judge_handler.py:184`'s
`hmac.compare_digest`. Anyone reaching port 9998 can inject `submission-request` packets attributed
to arbitrary submission IDs, or send `disable-judge` to take every judge offline. It binds to
`localhost` by default (`dmoj/settings.py:668`), so this is defence-in-depth today — but it becomes
real the moment the bridge and web tier are split across hosts or containers. *Fix:* add a shared
secret handshake; firewall the port regardless.

### 11. `judge/apps.py:36-51` swallows every exception and arms timers in every process
`ready()` runs for `migrate`, `makemigrations`, `shell`, `test`, `collectstatic` — everything. The
bare `except Exception: pass` hides genuine misconfiguration, and `reschedule_all_fso_contests()`
arms live timers in throwaway processes that exit before they fire. *Fix:* narrow the exception, log
it, and guard so scheduling only runs in the serving process.

### 12. A `threading.Timer` is stored in the Django cache
`judge/bridge/judge_handler.py:148-153` does `cache.set(cache_key, timer, ...)`. This only works
because `default` is `LocMemCache`, which stores objects by reference. Point `default` at Redis — a
plausible change, since the project already uses `django_redis` for the realtime cache — and every
FSO grading-end raises on pickling a `Lock`. *Fix:* use the module-level dict + lock pattern already
present in `fso_scheduler.py`.

### 13. FSO rescores twice per submission
`judge/bridge/judge_handler.py:521` calls `update_contest()`, which already ends in
`recompute_results()` (`judge/models/submission.py:256-279`), *before* the debounce block at
`:533-544` schedules another. The comment at `judge/tasks/contest.py:298-299` shows the debounce was
believed to replace the per-submission rescore. It does not — it is pure extra work on top.

### 14. Mirror cycles can be created concurrently
`Problem.save()` reads the chain via `resolve_mirror_root_id` with no `select_for_update` and no
wrapping transaction, so two concurrent saves can persist `A→B` and `B→A`. `io_method`
(`:706-709`) then recurses unboundedly and raises `RecursionError` on any page touching either
problem. `resolve_mirror_root_id`'s cached-shortcut branch (`problem_mirror.py:91-94`) trusts a
stored `mirror_root_id` without re-walking, so the corruption propagates silently to new mirrors.
Worth noting: **`select_for_update` appears nowhere in this codebase.**

### 15. SVG uploads are not sanitized
`MARTOR_UPLOAD_SAFE_EXTS` (`dmoj/settings.py:639`) permits `.svg`, stored as-is. Opened directly
(not via `<img>`), embedded script executes in the site origin. Reachable by any
`is_staff`/`can_upload_image` account. *Fix:* drop `.svg`, or sanitize, or serve media from a
cookie-less origin with `Content-Disposition: attachment`.

### 16. A swallowed exception can leak FSO scores mid-contest
`judge/judgeapi.py:108-110` wraps the FSO "keep this submission Pending" check in
`except Exception: pass`. If that lookup raises for any reason, execution falls through to **normal
immediate judging** — a contestant sees their score during a contest whose entire premise is that
they cannot. Silent, with no logging.

### 17. `X-Forwarded-For` is trusted with no proxy allowlist
`judge/middlewares/user_activity.py:174-179` takes the first XFF entry unconditionally, and that IP
is written into the staff-visible audit trail. Any user can poison it if the proxy ever fails to
strip the header. `judge/ip_auth.py`'s `REMOTE_ADDR` default is fine — the risk is repointing
`IP_BASED_AUTHENTICATION_HEADER` at an XFF-derived header without a trusted proxy in front.

### 18. N+1 queries in FSO scoring
`judge/contest_format/final_submission.py:58-79` issues one query per problem per participant to find
"last submission", on every `recompute_results()` — which, per finding 13, runs very often.

---

## P3 — Technical debt and future work

### 19. Delete ~832 lines of dead user-activity code
Confirmed zero references anywhere (settings, urls, templates, imports):

- `judge/middleware/` — the entire singular directory (160 lines)
- `judge/middlewares/user_activity.py` (171 lines)
- `judge/middlewares/user_activity_safe.py` (228 lines)
- `judge/views/user_activity_safe.py` (83 lines)

Only `judge.middlewares.user_activity_batch.BatchUserActivityMiddleware` is wired
(`dmoj/settings.py:443`). Git history shows these are an evolutionary trail — the batch version has
been iterated on since, the others untouched since 2025-11-02.

Two related oddities: neither middleware directory has `__init__.py` (they work as PEP 420 implicit
namespace packages, inconsistent with every other package here), and `judge/legacy_middleware.py`
exists purely so `judge/middleware.py` (a *file*) can coexist with `judge/middleware/` (a
*directory*). Three near-identically-named entities is a genuine footgun. Already flagged in
[`docs/codebase-map.md`](docs/codebase-map.md).

### 20. Test coverage
All 123 tests are model/utility tests. **There are no view tests at all** — no `Client.get()`
anywhere in the suite. Untested entirely:

- FSO contest format and scheduler — the subject of P0 finding 1
- User-activity tracking — iterated on live in production, with commits like *"fix: critical bug in
  sessions_map causing null session references"*
- The bridge (`echo_test_server.py` / `echo_test_client.py` are manual scripts, not `TestCase`s, and
  are never collected by the test runner)

Mirroring is only partially tested (`judge/models/tests/test_problem.py:484-494` covers
`validate_mirror_source_for_target` and `get_mirrorable_source_queryset`);
`resolve_mirror_root_id` and `rebuild_mirror_descendants` are not.

`judge/test_external_judge_async.py` is a genuine, properly mocked `TestCase` (15 tests, no network)
— just misplaced at the app root instead of under `judge/models/tests/`.

**Suggested order:** regression tests for findings 1, 2 and 5 first, then a view-test harness, then
backfill.

### 21. CI gaps
- `npm run format:check` exists in `package.json` but is never run — Prettier formatting of
  `websocket/` can drift silently.
- No `makemigrations --check`, so a missing migration only surfaces in production.
- No dependency audit or security scanning (`pip-audit`, `npm audit`, Dependabot) — compounds
  finding 6.
- Coverage is uploaded but gating is disabled in `codecov.yml` (`project: off`, `patch: off`), so it
  is decorative.
- `.github/workflows/caniuse.yml` and `updatemessages.yml` are gated to
  `github.repository == 'DMOJ/online-judge'` and can never run here. Consequence:
  `resources/caniuse.json` (7.3 MB) will go stale indefinitely.

### 22. Split the largest files
`judge/views/contests.py` (1964 lines), `judge/views/problem.py` (1356),
`judge/models/contest.py` (1240), `judge/views/problem_data.py` (1025).

### 23. Repo hygiene
- Move `fix_fso_points.py` (repo root) to `judge/management/commands/` — it hand-rolls
  `django.setup()` when `BaseCommand` already exists for this, and it would become discoverable and
  testable.
- Delete `templates/qhhoj_summer_challenge_2024.html`; its only reference
  (`dmoj/urls.py:217-218`) is already commented out.

### 24. Ambiguity worth cleaning up
- `EXTERNAL_JUDGE_ALLOW_HTTP = DEBUG` (`dmoj/settings.py:66`) couples a security setting to a debug
  flag. A deployment that forgets to set `DEBUG = False` silently permits plaintext external-judge
  traffic, and the names give no hint of the connection.
- `INSTALLED_APPS = ()` then conditional `+=` (`:301-400`) makes Django app ordering — which affects
  template and static resolution — depend on whether `wpadmin` happens to import.

### 25. TODO/FIXME inventory
Nine sites. Notable: the same `FIXME` about `is_accessible_by` refactoring appears twice
(`judge/views/submission.py:679` and `:940`, referencing upstream issue #1509), and
`judge/views/user.py:191` self-acknowledges duplication with `problem.py`. Others:
`templates/base.html:47`, `judge/jinja2/submission.py:8`, `judge/utils/diggpaginator.py:193`,
`judge/utils/problem_data.py:93` (bare `# TODO:` with no explanation),
`judge/utils/codeforces_polygon.py:383`, `judge/views/error.py:12`.

### 26. Local development is blocked
Python 3.14 (the only interpreter on this machine) versus `Django>=5.1,<5.2`, which supports
3.10–3.13. See [`docs/local-setup.md`](docs/local-setup.md). Finding 7 resolves this.

---

## Diagnosing the FSO issue on the live server

Before changing anything, determine which trigger path is active — it decides the blast radius.

| Path | Worst case |
|---|---|
| **Cron** running `check_fso_contests` | Worst. Every tick is a fresh process with an empty `LocMemCache`, so **every ended FSO contest is rejudged on every tick**. |
| **Celery beat** | Every ended FSO contest rejudged every 24 h (cache TTL), plus immediately on every worker restart. |
| **Timer only** (no periodic trigger) | No 24 h loop, but concurrent duplicate judging across uwsgi workers still applies. |

```bash
# Which processes are running?
sudo supervisorctl status
grep -rn "beat" /etc/supervisor/conf.d/

# Is it driven by cron instead?
crontab -l | grep -i fso
sudo crontab -l | grep -i fso

# How often has it actually fired?
grep -c "=== Periodic check for FSO contests started ===" <celery log>
grep "Triggering judging for contest" <celery log>
```

Measure the damage — submissions rejudged long after they were made:

```sql
SELECT c.key, COUNT(*) AS n, MAX(s.rejudged_date) AS last_rejudge
FROM judge_submission s
JOIN judge_contestsubmission cs ON cs.submission_id = s.id
JOIN judge_contestparticipation p ON cs.participation_id = p.id
JOIN judge_contest c ON p.contest_id = c.id
WHERE c.format_name = 'final_submission' AND s.rejudged_date IS NOT NULL
GROUP BY c.key
ORDER BY last_rejudge DESC;
```

A quick mitigation if you need one before deploying the fix: set `auto_judge: false` in
`format_config` on already-finished FSO contests — every trigger path honours it.

**After deploying the fix**, run the migration and confirm the backfill took:

```bash
./manage.py migrate judge 0219
```
```sql
-- Every already-ended FSO contest should now be marked as judged, so nothing re-fires.
SELECT COUNT(*) FROM judge_contest
WHERE format_name = 'final_submission' AND end_time <= NOW() AND fso_judged_end_time IS NULL;
-- expected: 0
```

Note that the periodic task is much quieter now — it only logs when it actually triggers something,
so `=== Periodic check for FSO contests started ===` no longer appears every minute. Its absence
after deploying is expected, not a sign the task stopped running.

---

## Checked and found to be fine

Recorded so these are not re-investigated:

**Virtual judge** — Fernet handling raises `ImproperlyConfigured` when the key is missing, with no
insecure fallback; `EXTERNAL_JUDGE_ALLOW_HTTP` is genuinely enforced
(`judge/utils/external_judge_client.py:81-86`); the API token is never logged;
`poll_external_submission` is properly idempotent via an `expected_pcd_submission_id` correlation
token (`judge/external_judge.py:280-294`, `:352-379`) — well-designed defensive code; poll timeout
correctly terminates at `IE` rather than leaving a dangling `P`; verdict-mapping fallbacks are
complete with no silent drop; `max_retries=None` is safe because both the 30-minute timeout and
`max_poll_attempts` are checked before any retry.

**Public ranking links** — ~107 bits of entropy via `secrets.choice`; expiry re-checked live on every
request; null `expiry_amount` rejected at both view and model layer; `IntegrityError` retry on token
collision is race-safe; timezone handling is consistent; no PII in the ranking payload.

**User activity** — the raw SQL at `judge/views/user_activity.py:144,191` is fully parameterized (the
one `.format()` inserts a static literal chosen by an internal boolean); `admin/active-users/` and
`admin/all-logs/` are gated behind a real custom permission.

**General** — zip handling never extracts by entry name and uses `os.path.commonpath` for path
traversal defence; judge auth uses `hmac.compare_digest`; no `pickle` or unsafe `yaml.load`
anywhere; `subprocess` calls use list-form args with no `shell=True`; API v2 is read-only and scopes
every queryset through the visibility helpers; migrations 0214–0218 are pure schema operations and
auto-reversible; `ContestParticipation.recompute_results()` is idempotent, so the absence of
`select_for_update` there is not a lost-update risk.

**Mirroring** — `resolve_mirror_root_id` does detect cycles via a `seen` set in the single-writer
case (the race in finding 14 is the concurrent case only);
`sync_mirror_archive_for_problem` is a deliberate no-op stub, so it has no path-traversal surface —
though callers reading its return count will always see "0 changed", which is worth a UI note.
