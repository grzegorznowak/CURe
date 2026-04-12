# Public Release Evidence

Store Story 05 prove-out logs here.

Each release evidence file should use a dated name and capture the command transcript summary for one prove-out target, such as local artifact smoke or PyPI.

Keep the evidence portable:

- use repo-relative commands where possible
- replace machine-specific temp roots and home directories with placeholders such as `<temp-root>`
- include exact artifact names, versions, tags, and outcomes
- include literal error text only when it is relevant to the blocker
- avoid host-specific paths unless they are themselves part of the failure being documented

Required fields:

- Status
- Version / tag
- Target
- Commands run
- Changelog entry shipped
- Verified public command surface
- What worked
- Blockers / risks
- Rollback / hotfix decision
- Exact next operator action
