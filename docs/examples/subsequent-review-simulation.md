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
