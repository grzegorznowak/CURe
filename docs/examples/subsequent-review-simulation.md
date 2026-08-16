# Subsequent Review Simulation

> **Synthetic fixture:** this page is a dummy PR history for design discussion only. It is not a record of a real GitHub PR, real CURe output, or real product decisions.

This example shows the behavior expected from future CURe subsequent-review support when a fresh review is run after earlier CURe reviews and human PR discussion already exist. The fixture intentionally separates:

- **source verification**: what the current branch proves in code;
- **discussion resolution**: what maintainers, reviewers, or product owners said about scope and intent;
- **final arbitration**: what CURe should report, suppress, confirm, or escalate.

## Simulated PR

- Repository: `grzegorznowak/CURe`.
- PR: `#9999` / `feature/review-ledger-demo` into `main`.
- Title: `Add persisted review disposition ledger`.
- Head SHA at final review: `deadbeef9999`.
- Changed files in this dummy scenario:
  - `cure.py`
  - `cure_flows.py`
  - `prompts/mrereview_gh_local.md`
  - `tests/test_review_ledger.py`

## User-Facing Scenario Setup

This section mocks what an operator might see before CURe produces the final review. The command output and artifact names are proposed UX, not current behavior.

### Existing CURe history discovered locally

| Session | Reviewed head | Artifact | Outcome CURe would summarize |
| --- | --- | --- | --- |
| `session-a` | `abc1111` | `.cure/reviews/pr-9999/session-a/review.md` | 5 prior findings: A-01 through A-05. |
| `session-b` | `def2222` | `.cure/reviews/pr-9999/session-b/review.md` | 6 prior findings: B-01 through B-06. |

CURe should make it clear that both prior reviews are older than the current head `deadbeef9999`; they are inputs for retrospective verification, not final truth.

### Existing GitHub discussion discovered remotely

| Discussion source | Count in this simulation | User-facing note |
| --- | ---: | --- |
| Issue comments | 6 | Includes developer claims, maintainer scope decisions, and security-owner escalation. |
| Review comments | 2 | Includes product-owner clarification and low-authority pushback. |
| Review thread states | 2 | One resolved thread and one unresolved thread; thread state is a hint only. |
| Review bodies | 0 | None in this scenario, but the fetch step reports that it checked. |
| Timeline / external references | 1 | CURe-123 is linked from maintainer discussion C-04. |

### Simulated GitHub timeline

```text
T+00  bob-dev opens PR #9999 at head abc1111.
T+05  CURe review A is posted with A-01..A-05.
T+12  bob-dev pushes def2222 and claims A-05 is fixed.
T+15  cara-product clarifies JSON compatibility requirements.
T+18  alice-reviewer moves GraphQL thread fetching to CURe-123.
T+25  CURe review B is posted with B-01..B-06.
T+31  alice-reviewer marks A-03 superseded by B-03 and leaves B-03 unresolved.
T+33  bob-dev claims B-04 is accepted risk.
T+34  security-owner rejects B-04 suppression.
T+40  bob-dev pushes deadbeef9999 and asks for a fresh CURe review.
```

## Simulated CLI Interaction

### Default interactive run

```text
$ cure pr https://github.com/grzegorznowak/CURe/pull/9999

CURe found prior completed reviews for grzegorznowak/CURe#9999:
  [1] session-a  head=abc1111  completed=2026-06-03T09:05Z  findings=5
  [2] session-b  head=def2222  completed=2026-06-03T09:25Z  findings=6

CURe also found existing PR discussion after the first CURe review:
  issue comments: 6
  review comments: 2
  review threads: 2 (1 resolved, 1 unresolved)
  linked external references: CURe-123

How should this run proceed?
  new     run a new review using prior-review and discussion context
  latest  show the latest completed CURe review instead
  list    list prior completed reviews and exit
  cancel  exit without reviewing
Choice [new/latest/list/cancel]: new
```

### Non-interactive policy examples

```text
$ cure pr https://github.com/grzegorznowak/CURe/pull/9999 --if-reviewed list
Found 2 completed reviews for grzegorznowak/CURe#9999.
- session-a  head=abc1111  review=.cure/reviews/pr-9999/session-a/review.md
- session-b  head=def2222  review=.cure/reviews/pr-9999/session-b/review.md

$ cure pr https://github.com/grzegorznowak/CURe/pull/9999 --if-reviewed latest
Opening latest completed review: .cure/reviews/pr-9999/session-b/review.md

$ cure pr https://github.com/grzegorznowak/CURe/pull/9999 --if-reviewed new
Starting a new subsequent review at head deadbeef9999.
```

### Preflight context summary shown before analysis

```text
Subsequent-review context summary:
- Prior CURe reviews loaded: 2
- Prior findings extracted: 11
- Potential duplicate/superseded groups: 1 (A-03 -> B-03)
- Prior findings needing source verification: 11
- PR discussion items linked to findings: 10
- Developer claims requiring source verification: C-02, C-10
- High-authority scope/product decisions: C-03, C-04, C-08
- Ambiguous or low-authority pushback: C-05
- High-severity conflicts: B-04 has author pushback C-07 and security-owner rejection C-08
```

### Progress output during the review

```text
[1/6] Fetching PR metadata and changed files... done (head=deadbeef9999)
[2/6] Fetching PR discussion... done (10 relevant items, 1 external reference)
[3/6] Loading prior CURe reviews... done (2 reviews, 11 findings)
[4/6] Verifying prior findings against current source... done
[5/6] Resolving discussion dispositions... done
[6/6] Arbitrating final report actions... done

Warnings:
- Resolved GitHub threads are treated as hints only; they do not prove source resolution.
- Developer "fixed" comments are claims only; C-10 was rejected by current source evidence.
- GraphQL review-thread coverage is out of scope for this PR only because maintainer C-04 links CURe-123.
- Critical finding B-04 remains visible because author accepted-risk pushback C-07 lacks security authority and is rejected by C-08.
```

### Generated context artifacts

```text
<session_dir>/work/
  pr-context.json
  pr-discussion-context.json
  prior-cure-reviews.json
  prior-finding-source-verification.md
  comment-resolution-ledger.md
  finding-disposition-ledger.json
  review.subsequent-context.summary.md
```

| Artifact | Purpose |
| --- | --- |
| `pr-context.json` | PR metadata, refs, head SHA, changed files, and current review mode. |
| `pr-discussion-context.json` | Normalized comments, reviews, thread states, authors, authority hints, and external references. |
| `prior-cure-reviews.json` | Prior CURe sessions, artifact paths, heads reviewed, and extracted finding summaries. |
| `prior-finding-source-verification.md` | Source-only verification ledger for prior findings. |
| `comment-resolution-ledger.md` | Discussion-only disposition ledger. |
| `finding-disposition-ledger.json` | Combined source/discussion arbitration data for prompts and future runs. |
| `review.subsequent-context.summary.md` | Human-readable audit summary included beside the final review. |

## Prior CURe Review A

Simulated artifact: `.cure/reviews/pr-9999/session-a/review.md`.

```markdown
**Summary**: The PR starts a persisted review ledger, but the first version conflates comment disposition with source truth.

## Business / Product Assessment
### In Scope Issues

- [A-01][Medium] Resolved GitHub threads are treated as proof that findings are fixed.
  Evidence: `cure.py:4120-4167` sets `source_state="resolved"` when `thread.isResolved` is true.
  Impact: A reviewer can click Resolve Conversation while the defect still exists.

- [A-02][Low] Product says CLI JSON output must remain stable, but the PR renames `review_id` to `finding_id` without compatibility handling.
  Evidence: `cure_flows.py:821-846` writes only `finding_id`.

## Technical Assessment
### In Scope Issues

- [A-03][High] Prior findings are de-duplicated only by their rendered title.
  Evidence: `cure.py:4294-4310` uses `normalized_title` as the dictionary key.
  Impact: two different defects with similar headings collapse into one ledger row.

- [A-04][Medium] Review comments are fetched but review bodies are ignored.
  Evidence: `cure.py:4017-4044` calls `/pulls/comments` but not `/pulls/{number}/reviews`.

- [A-05][Medium] Source verification trusts developer comments that say "fixed".
  Evidence: `cure.py:4172-4188` maps `/fixed/i` to `resolved_from_source` without reading the patched file.
```

## Prior CURe Review B

Simulated artifact: `.cure/reviews/pr-9999/session-b/review.md`.

```markdown
**Summary**: The second pass sees partial progress, but important threading and arbitration gaps remain.

## Business / Product Assessment
### In Scope Issues

- [B-01][Medium] `--json` still emits unstable ledger field names in follow-up summaries.
  Evidence: `cure_flows.py:913-934` emits `review_id` in one path and `finding_id` in another.

- [B-02][Low] The report re-requests work that maintainers explicitly moved to CURe-123.
  Evidence: PR discussion says GraphQL resolved-thread fetching is split to CURe-123, but the review still lists it as required for this PR.

## Technical Assessment
### In Scope Issues

- [B-03][High] Duplicate detection now uses title plus file, but still misses line movement.
  Evidence: `cure.py:4315-4349` hashes `title:file:line`.

- [B-04][Critical] High-severity secret-leak warnings can be dismissed by any comment containing "accepted risk".
  Evidence: `cure.py:4388-4406` does not check commenter authority or source state before suppressing the finding.

- [B-05][Medium] Retrospective verification cannot cite the source lines used to confirm resolution.
  Evidence: `cure_flows.py:1001-1039` writes status but no provenance.

- [B-06][Medium] REST comment pagination can miss later PR discussion.
  Evidence: `cure.py:4079-4092` reads only the first page of comments.
```

## PR Discussion Transcript

All comments are synthetic. `Authority` is the proposed resolver's normalized authority level, not a GitHub permission claim.

| ID | Kind | Author / authority | Excerpt | Linked finding(s) | Expected resolver classification |
| --- | --- | --- | --- | --- | --- |
| C-01 | review thread, resolved | `alice-reviewer` / maintainer | "I resolved this thread after seeing `verify_source_state()` added. Please still cite source lines in the final report." | A-01, B-05 | `resolved_thread` hint only; source still must prove resolution. |
| C-02 | issue comment | `bob-dev` / PR author | "A-05 is fixed now; I changed the regex path so comments cannot mark source resolved." | A-05 | `developer_claim_fixed`; verify from source, do not accept comment as proof. |
| C-03 | review comment | `cara-product` / product owner | "The JSON schema intentionally keeps both `review_id` and `finding_id` for two releases. Please treat dual fields as by-design compatibility." | A-02, B-01 | `by_design`/business-rule clarification; retarget source check to compatibility behavior. |
| C-04 | issue comment | `alice-reviewer` / maintainer | "GraphQL review-thread resolution is important but split out to CURe-123. This PR only needs REST comment/review coverage." | A-04, B-02 | `addressed_elsewhere` with external reference `CURe-123`. |
| C-05 | review comment | `dave-intern` / low authority | "Duplicate hashing seems fine; please don't block on it." | A-03, B-03 | `ambiguous_low_authority_pushback`; should not suppress if source remains open. |
| C-06 | review thread, unresolved | `alice-reviewer` / maintainer | "Line-movement still breaks fingerprints after the latest push." | B-03 | `unresolved_thread`; increases confidence to re-report if source agrees. |
| C-07 | issue comment | `bob-dev` / PR author | "The secret-leak warning is accepted risk because this is an internal-only tool." | B-04 | `explicit_pushback` but insufficient authority for high severity; source must remain visible or escalate. |
| C-08 | issue comment | `security-owner` / security authority | "Do not suppress B-04 without a coded allowlist and audit trail. Internal-only is not an exception." | B-04 | authoritative rejection of suppression. |
| C-09 | issue comment | `alice-reviewer` / maintainer | "A-03 and B-03 are duplicates; B-03 supersedes A-03 because it describes the remaining line-movement gap." | A-03, B-03 | `duplicate_superseded`; keep B-03 as canonical. |
| C-10 | issue comment | `bob-dev` / PR author | "B-06 is fixed now; I added pagination handling in the comment fetcher." | B-06 | `developer_claim_fixed`; verify from source and re-report if source rejects the claim. |

## Current Source Snapshot For The Final Review

The final review runs after another push. These excerpts are synthetic source facts that the retrospective engine discovered.

| Source ID | Synthetic location | Fact |
| --- | --- | --- |
| S-01 | `cure.py:4102-4149` | `verify_source_state()` now reads the patched file and writes `resolved_thread_hint=true` separately from `source_state`. |
| S-02 | `cure.py:4155-4182` | A comment containing `fixed` is stored as `developer_claim` but cannot set `source_state`. |
| S-03 | `cure_flows.py:905-947` | Both `review_id` and `finding_id` are emitted in JSON output, with `review_id` marked deprecated. |
| S-04 | `cure.py:4021-4078` | REST issue comments, review comments, and review bodies are fetched; GraphQL resolved-thread state is not fetched. |
| S-05 | `cure.py:4315-4368` | Fingerprints use `title:file:line`, so moving code by five lines changes the fingerprint. |
| S-06 | `cure.py:4388-4412` | A finding is suppressed when any comment matches `/accepted risk/i`, even if the author is not a security authority. |
| S-07 | `cure_flows.py:1001-1044` | Retrospective rows include `source_state` and `discussion_disposition`, but only one citation slot. |
| S-08 | `cure.py:4079-4092` | REST comment pagination stops after the first page of 100 comments. |

## Retrospective Source Verification Ledger

This ledger answers: "What does the current source prove about each prior CURe finding?" Discussion is included only as a hint or retargeting context.

| Prior finding | Source state | Source evidence | Notes |
| --- | --- | --- | --- |
| A-01 | `resolved_from_source` | S-01 | Resolved-thread state no longer proves resolution; thread status is stored as a hint. |
| A-02 | `resolved_from_source` after retarget | S-03 | Product clarified compatibility target in C-03; current source satisfies that clarified rule. |
| A-03 | `superseded_by_new_issue` | S-05 | Same defect family as B-03; C-09 says B-03 is the canonical remaining issue. |
| A-04 | `partially_resolved` | S-04 | REST reviews are covered, but GraphQL thread resolution remains out of this PR by C-04. |
| A-05 | `resolved_from_source` | S-02 | Developer claim C-02 was verified against source; the comment alone was not proof. |
| B-01 | `resolved_from_source` after retarget | S-03 | Same compatibility issue as A-02. |
| B-02 | `still_open_but_out_of_scope` | S-04 | GraphQL coverage absent, but maintainer C-04 split it to CURe-123. |
| B-03 | `still_open` | S-05 | Current fingerprint still changes when lines move; C-06 is matching unresolved discussion. |
| B-04 | `still_open` | S-06 | High-severity suppression still trusts insufficient-authority comments. |
| B-05 | `partially_resolved` | S-07 | Verification rows exist, but citation model is too weak for multiple source/discussion citations. |
| B-06 | `still_open` | S-08 | Developer claim C-10 says pagination was fixed, but source still stops after the first page. |

## Comment Resolver Ledger

This ledger answers: "What did PR discussion establish about reportability, authority, and scope?"

| Finding / topic | Discussion disposition | Authority and recency | Citations | Recommended effect |
| --- | --- | --- | --- | --- |
| A-01 | `resolved_thread` | Maintainer, current | C-01 | Treat as a hint only; rely on S-01 for confirmation. |
| A-02 / B-01 | `by_design_business_rule` | Product owner, current | C-03 | Suppress original incompatible-schema complaint; confirm dual-field compatibility from S-03. |
| A-04 / B-02 | `addressed_elsewhere` | Maintainer, current | C-04, CURe-123 | Do not re-request GraphQL thread coverage in this PR; mention tracked follow-up. |
| A-03 / B-03 | `duplicate_superseded` plus `unresolved_thread` | Maintainer, current | C-06, C-09 | Suppress A-03 duplicate; report B-03 as remaining canonical issue. |
| A-05 | `developer_claim_fixed` | Author, current | C-02 | No direct report effect; source verification determines outcome. |
| B-04 | `pushback_rejected_for_authority` | Author pushback rejected by security owner | C-07, C-08 | Keep visible as Critical until coded allowlist/audit trail exists. |
| B-06 / comment pagination | `developer_claim_fixed` | Author only | C-10 | Do not suppress from C-10; source shows first-page-only pagination in S-08, so re-report. |
| Low-authority duplicate pushback | `ambiguous_low_authority_pushback` | Low-authority, stale after C-06 | C-05 | No suppression. |

## Finding Matching And Deduplication Mockup

When multiple CURe reviews already exist, CURe should explain which old findings are distinct, which are repeated, and which newer finding supersedes an older one.

| Prior finding group | Match reason | Canonical issue for final review | User-visible action |
| --- | --- | --- | --- |
| A-01 | Same source area now has an explicit source/discussion split. | A-01 | Confirm resolved from source; do not re-report. |
| A-02, B-01 | Same JSON schema compatibility concern; product clarification C-03 retargets the expected behavior. | A-02/B-01 compatibility group | Confirm resolved after source verifies dual-field compatibility. |
| A-03, B-03 | Same defect family; C-09 says B-03 supersedes A-03, and source S-05 proves the remaining line-movement defect. | B-03 | Suppress A-03 as duplicate; report B-03 once. |
| A-04, B-02 | Same GraphQL thread coverage concern; C-04 moves it to CURe-123. | A-04/B-02 external-work group | Mark out of scope for this PR while noting source is only partially covered. |
| A-05 | Developer claim C-02 maps to the same comment-trust defect. | A-05 | Confirm resolved only after source S-02 proves comments no longer set source state. |
| B-04 | No duplicate; high-severity conflict with author pushback. | B-04 | Re-report with security-owner authority context. |
| B-05 | Same general provenance theme as A-01's resolved-thread comment, but a narrower remaining citation model defect. | B-05 | Reword as a smaller remaining technical issue. |
| B-06 | Developer says fixed in C-10, but source S-08 rejects the claim. | B-06 | Re-report; explain the rejected claim. |

## Conflict Resolution UX

CURe should surface comment conflicts instead of silently choosing one side.

```text
Conflict detected: B-04 high-severity suppression

Evidence from discussion:
  C-07 bob-dev / author: "accepted risk because this is internal-only"
  C-08 security-owner / security authority: "Do not suppress without coded allowlist and audit trail"

Evidence from source:
  S-06 suppression still triggers on any /accepted risk/i comment.

Decision:
  Keep B-04 visible as Critical. Author pushback is recorded but rejected for insufficient authority and later security-owner contradiction.
```

```text
Conflict detected: B-06 developer fixed claim

Evidence from discussion:
  C-10 bob-dev / author: "I added pagination handling"

Evidence from source:
  S-08 fetch still stops after the first page of 100 comments.

Decision:
  Re-report B-06. Comments alone cannot mark the finding resolved_from_source.
```

## Simulated GitHub Output Behavior

The final CURe run should avoid flooding the PR with duplicate comments. In this mockup CURe posts one new summary review and does not reopen resolved threads.

```text
GitHub posting plan:
- Post one new CURe review summary comment for head deadbeef9999.
- Include a "Prior CURe Finding Confirmations" section for resolved old findings.
- Include a "Suppressed / Out Of Scope" section with citations for C-03, C-04, and C-09.
- Include four current reportable issues under normal Business / Product and Technical headings.
- Do not post inline comments for A-01, A-02/B-01, A-03, A-04/B-02, or A-05.
- Do not mark any GitHub thread resolved from source unless source verification independently proves it.
```

Example GitHub summary comment:

```markdown
CURe subsequent review for `deadbeef9999`

Loaded prior CURe context:
- Review A: 5 findings at `abc1111`
- Review B: 6 findings at `def2222`
- PR discussion items linked: 10

Disposition summary:
- Confirmed resolved from source: A-01, A-05
- Confirmed resolved after product retarget: A-02/B-01
- Suppressed duplicate: A-03 -> B-03
- Out of scope with maintainer citation: A-04/B-02 -> CURe-123
- Re-reported: B-03, B-04, B-05, B-06

See the full review artifact for source and discussion citations.
```

## Visible Fallbacks And Limitations

A thorough user interaction should also show degraded modes. These messages keep failures explicit instead of letting CURe pretend it has complete context.

| Situation | User-visible behavior | Safe default |
| --- | --- | --- |
| GitHub comments API unavailable | Warn that PR discussion was not loaded and mark discussion dispositions `not_available`. | Do not suppress findings based on missing discussion. |
| Review threads unavailable without GraphQL | Load REST comments/reviews, mark thread-resolution state incomplete. | Treat resolved-thread claims as unverified hints. |
| Prior review artifact cannot be parsed | Report the artifact path and continue with parseable reviews only. | Do not claim full prior-review coverage. |
| Comment pagination incomplete | Warn that only a prefix of discussion was fetched. | Avoid final suppression decisions that depend on unseen later comments. |
| Author authority is unknown | Classify as `ambiguous` or `author_claim`. | Require source proof or maintainer/security confirmation. |
| External ticket reference is missing or ambiguous | Show the text that mentioned it and mark `external_reference_unverified`. | Keep source-open findings visible unless an authority explicitly scopes them out. |

## Final Simulated CURe Response With New Engines Enabled

```markdown
**Summary**: Subsequent-review intelligence is enabled for this run. CURe verified prior findings against the current source, separately classified PR discussion, and arbitrated report actions from both ledgers. Four prior findings across three groups are confirmed resolved, two are suppressed or moved out of scope with cited discussion provenance, and four issues remain reportable.

## Prior CURe Finding Confirmations

- Confirmed resolved: [A-01] resolved-thread hints no longer prove source resolution. Source now stores thread status separately from `source_state` (`cure.py:4102-4149`, S-01). C-01 was treated as a hint, not proof.
- Confirmed resolved after product retarget: [A-02]/[B-01] JSON compatibility now keeps both `review_id` and `finding_id` for the deprecation window (`cure_flows.py:905-947`, S-03), matching product clarification C-03.
- Confirmed resolved: [A-05] developer "fixed" comments no longer set source resolution directly (`cure.py:4155-4182`, S-02). C-02 was verified against source before closure.

## Suppressed, Reclassified, Or Out Of Scope

- Suppressed duplicate: [A-03] is superseded by [B-03] per maintainer discussion C-09. The canonical remaining issue is reported below.
- Moved out of scope: [A-04]/[B-02] GraphQL review-thread resolution remains absent from this PR (`cure.py:4021-4078`, S-04), but maintainer C-04 explicitly split it to CURe-123. Do not re-request it here.
- Reclassified partial improvement: [B-05] source-verification rows now exist but do not carry enough citation slots for mixed source/discussion provenance (`cure_flows.py:1001-1044`, S-07). Reported below as a narrower technical issue.

## Business / Product Assessment
### In Scope Issues

No product-blocking issues remain after applying the product-owner compatibility clarification C-03 and maintainer scope split C-04.

### Out Of Scope / Tracked Elsewhere

- GraphQL resolved-thread fetching is tracked in CURe-123. This run intentionally does not require it from PR #9999 because C-04 is recent maintainer direction.

## Technical Assessment
### In Scope Issues

- [High] Finding fingerprints still break when code moves.
  - Source evidence: `cure.py:4315-4368` hashes `title:file:line` (S-05), so the same defect receives a different fingerprint after nearby insertions or deletions.
  - Discussion evidence: C-06 says the thread remains unresolved after the latest push; C-09 marks B-03 as the canonical successor to A-03.
  - Arbitration: re-report. C-05 is low-authority and stale, so it does not suppress this issue.

- [Critical] High-severity secret-leak findings can still be suppressed by insufficient-authority comments.
  - Source evidence: `cure.py:4388-4412` suppresses on `/accepted risk/i` without checking security authority or requiring an allowlist/audit trail (S-06).
  - Discussion evidence: C-07 is author pushback only; C-08 from the security owner explicitly rejects suppression.
  - Arbitration: re-report and preserve Critical severity despite pushback.

- [Medium] Retrospective verification rows cannot cite multiple evidence types.
  - Source evidence: `cure_flows.py:1001-1044` stores status with only one citation slot (S-07).
  - Discussion evidence: C-01 asks that final reports cite source lines; mixed provenance is needed for source and discussion arbitration.
  - Arbitration: report the narrower remaining defect; do not repeat the broader B-05 wording.

- [Medium] REST comment pagination can miss later PR discussion.
  - Source evidence: `cure.py:4079-4092` stops after the first page of 100 comments (S-08).
  - Discussion evidence: C-10 is only an author claim that pagination was fixed; source verification rejects the claim.
  - Arbitration: re-report. Do not suppress from C-10 alone.
```

## Expected Engine Behavior Covered

- Source-confirmed resolved prior issue: A-01, A-05.
- Still-open prior issue re-reported: B-03.
- Partially fixed prior issue reworded to remaining defect: B-05.
- Developer claim verified only after source confirms it: A-05 / C-02 / S-02.
- Developer claim rejected by source verification: B-06 / C-10 / S-08.
- By-design business-rule clarification: A-02 / B-01 / C-03 / S-03.
- Extracted or escalated elsewhere: A-04 / B-02 / C-04 / CURe-123.
- Duplicate or superseded finding: A-03 superseded by B-03 via C-09.
- Ambiguous or low-authority pushback: C-05.
- Resolved thread treated as hint, not proof: C-01 and A-01.
- High-severity pushback edge: B-04 / C-07 / C-08 / S-06.
- User-facing prior-review discovery and `--if-reviewed` interactions.
- Preflight summary of loaded prior reviews, linked comments, authority hints, and high-severity conflicts.
- Progress output for metadata fetch, discussion fetch, prior-review loading, source verification, comment resolution, and final arbitration.
- Auditable generated context artifacts under `work/`.
- Deduplication explanation for overlapping prior CURe findings.
- GitHub posting behavior that avoids duplicate comments while preserving suppressed/out-of-scope provenance.
- Visible degraded-mode fallbacks for missing comments, threads, prior artifacts, pagination, authority, and external references.
