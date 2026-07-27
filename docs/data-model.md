# Data model

All models live in `judge/models/` and are re-exported through `judge/models/__init__.py`. There is
one Django app (`judge`), so every table is `judge_*`.

## Files and their classes

| File | Classes |
|---|---|
| `problem.py` | `Problem`, `ProblemType`, `ProblemGroup`, `License`, `ProblemTranslation`, `ProblemClarification`, `LanguageLimit`, `Solution`; enums `SubmissionSourceAccess`, `ProblemTestcaseAccess`, `ProblemTestcaseResultAccess` |
| `contest.py` | `Contest`, `ContestTag`, `ContestAnnouncement`, `ContestParticipation`, `ContestProblem`, `ContestSubmission`, `Rating`, `ContestMoss`, `ContestPublicRankingLink` |
| `profile.py` | `Profile`, `Organization`, `Badge`, `OrganizationRequest`, `WebAuthnCredential`, `EncryptedNullCharField` |
| `submission.py` | `Submission`, `SubmissionSource`, `SubmissionTestCase`, `SUBMISSION_RESULT` |
| `runtime.py` | `Language`, `RuntimeVersion`, `Judge` |
| `problem_data.py` | `ProblemData`, `ProblemTestCase`, `CHECKERS`, `problem_data_storage` |
| `external_judge.py` | `ExternalJudgeConfig`, `ExternalProblem`, `ExternalSubmission` |
| `comment.py` | `Comment`, `CommentLock`, `CommentVote` |
| `interface.py` | `BlogPost`, `BlogVote`, `MiscConfig`, `NavigationBar` |
| `tag.py` | `TagGroup`, `Tag`, `TagProblem`, `TagData` |
| `ticket.py` | `Ticket`, `TicketMessage`, `GeneralIssue` |
| `user_activity.py` | `UserActivity`, `UserSession` |
| `urlshortener.py` | `URL` |
| `choices.py` | Shared choice tuples (`ACE_THEMES`, `TIMEZONE`, `MATH_ENGINES_CHOICES`, …) |

## The core graph

```
  auth.User ──1:1── Profile ──M2M── Organization
                       │                  │
                       │                  ├─M2M─ Problem   (org-private problems)
                       │                  └─M2M─ Contest   (org-private contests)
                       │
        ┌──────────────┼───────────────────┐
        │              │                   │
   Submission    ContestParticipation   Comment / Ticket / BlogPost
        │              │
        │              └── Rating  (per-contest Elo result)
        │
        ├─1:1─ SubmissionSource
        ├─1:N─ SubmissionTestCase
        └─1:1─ ExternalSubmission        (virtual judge only)


   Problem ──FK── ProblemType / ProblemGroup / License
      │
      ├─M2M─ Profile        (authors, curators, testers — three separate M2Ms)
      ├─self-FK─ Problem    (mirroring: a mirror points at its source)
      ├─1:1── ProblemData ──1:N── ProblemTestCase
      ├─1:1── ExternalProblem ──FK── ExternalJudgeConfig
      ├─1:N── LanguageLimit / ProblemTranslation / ProblemClarification / Solution
      └─1:N── Submission


   Contest ──M2M(through ContestProblem)── Problem
      │              │
      │              └── ContestSubmission ──1:1── Submission
      ├─1:N── ContestParticipation
      ├─1:N── ContestAnnouncement
      └─1:N── ContestPublicRankingLink


   Judge ──M2M── Language        (runtimes this judge provides)
     │   ──M2M── Problem         (problems whose data this judge has)
     └──1:N── RuntimeVersion
```

### Notes on the tricky bits

- **`Profile`, not `User`.** Almost every foreign key to "a user" points at `judge.Profile`, not
  `auth.User`. `Profile` holds points, rating, rank, timezone, language, and organization
  membership. `judge/apps.py:ready()` backfills a `Profile` for any profileless `User`.
- **Three authorship M2Ms on `Problem`** — authors, curators, testers — with different permission
  semantics. Check `Problem.is_editable_by()` rather than reasoning about them directly.
- **`ContestSubmission` is a join table with state.** A `Submission` made during a contest gets a
  `ContestSubmission` linking it to the `ContestProblem` and `ContestParticipation`; contest scoring
  reads that, not `Submission` directly.
- **`ContestParticipation` is per *attempt*.** Virtual participation means one user can have several
  rows for the same contest; `virtual` distinguishes them.
- **`Judge` is a *judge server* record**, not a person. Its `auth_key` is what the judge daemon
  presents to the bridge.

## Submission status vocabulary

Two separate fields, defined at the top of `judge/models/submission.py`:

`status` — where the submission is in the pipeline:

| Code | Meaning |
|---|---|
| `QU` | Queued |
| `P` | Processing |
| `G` | Grading |
| `D` | Completed |
| `PD` | Pending |
| `IE` | Internal Error |
| `CE` | Compile Error |
| `AB` | Aborted |

`result` — the verdict, only meaningful once `status='D'`:

| Code | Meaning |
|---|---|
| `AC` | Accepted |
| `WA` | Wrong Answer |
| `TLE` | Time Limit Exceeded |
| `MLE` | Memory Limit Exceeded |
| `OLE` | Output Limit Exceeded |
| `IR` | Invalid Return |
| `RTE` | Runtime Error |
| `CE` | Compile Error |
| `IE` | Internal Error |
| `SC` | Short Circuited |
| `AB` | Aborted |
| `RJ` | Rejected |

`Submission.IN_PROGRESS_GRADING_STATUS = ('QU', 'P', 'G')` is what `judge/bridge/daemon.py` sweeps to
`IE` on bridge restart. `SubmissionTestCase.status` uses the `result` vocabulary.

Status codes as the judge reports them are documented at
[docs.qhhoj.com/judge/status_codes.md](https://docs.qhhoj.com/judge/status_codes.md).

## Contest formats

Scoring is a plugin system, not `if` statements. `judge/contest_format/registry.py` provides a
`register_contest_format(name)` decorator populating a `formats` dict; `judge/contest_format/base.py`
defines the interface (update participation, compute ranking, render labels). `Contest.format_name`
selects one and `Contest.format_config` carries a JSON blob of per-format options.

Nine formats are registered in `judge/contest_format/__init__.py`:

| Format | File | Notes |
|---|---|---|
| Default | `default.py` | Sum of best per problem; any submission adds time penalty. |
| IOI | `ioi.py` | Max per subtask, summed. `cumtime` option. |
| Legacy IOI | `legacy_ioi.py` | Codechef-style IOI ranklist. |
| ECOO | `ecoo.py` | Last submission per problem; first-AC and speed bonuses. |
| AtCoder | `atcoder.py` | Penalty-based tiebreak (default 5 min). |
| ICPC | `icpc.py` | Problems solved, penalty tiebreak (default 20 min). |
| Ultimate | `ultimate.py` | |
| **VNOJ** | `vnoj.py` | VNOJ's own format, frozen ranking via raw SQL. |
| **Final Submission** | `final_submission.py` | QHHOJ's FSO format — see [qhhoj-features.md](qhhoj-features.md). |

Scoring semantics for the upstream eight are documented at
[docs.qhhoj.com/site/contest_formats.md](https://docs.qhhoj.com/site/contest_formats.md).

## Where problem data actually lives

Two halves that must stay in sync:

1. **On disk**, under `DMOJ_PROBLEM_DATA_ROOT` — one directory per problem code containing the test
   archive and an `init.yml`. This is the directory the judge servers mount (as `/problems` in the
   Docker setup). The judge reads `init.yml`; Django writes it.
2. **In the database** — `ProblemData` (1:1 with `Problem`: archive, checker, grader config) and
   `ProblemTestCase` (per-case points, type, generator, checker).

`judge/views/problem_data.py` is the editor that renders the DB rows and regenerates `init.yml`.
`judge/utils/problem_data.py` does the YAML generation. The
[problem format docs](https://docs.qhhoj.com/problem_format/problem_format.md) describe the YAML the
judge consumes, plus custom checkers, graders, and generators.

Because both site and judge need this directory, a single-machine dev setup points
`DMOJ_PROBLEM_DATA_ROOT` and the judge's bind mount at the same path.

## Version history

`judge/models/__init__.py` registers a subset of models with `django-reversion`, giving them admin
history and rollback: `Profile` (excluding `points`, `last_access`, `ip`, `rating`), `Problem`
(following `language_limits`), `LanguageLimit`, `Contest` (following `contest_problems`),
`ContestProblem`, `Organization`, `BlogPost`, `Solution`, `Judge` (name/created/auth_key/description
only), `Language`, `Comment`, `TagProblem`, `TagData`.

`Submission` is registered with `follow=['test_cases']` at its own definition site.

## Migrations

142 numbered migrations in `judge/migrations/` (plus `__init__.py`). The most recent five are the
QHHOJ feature timeline:

| Migration | Feature |
|---|---|
| `0214_create_user_activity_models` | Realtime user activity tracking |
| `0215_add_final_submission_format` | FSO contest format |
| `0216_problem_mirroring` | Problem mirroring |
| `0217_external_judge` | Virtual judge / external OJ |
| `0218_contestpublicrankinglink` | Public contest ranking links |

Migrations are excluded from flake8, so lint will not complain about generated files.
