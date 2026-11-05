# Cross-project delivery checklist

Record a short evidence trail for each feature or fix.

- [ ] Goal and acceptance criteria stated.
- [ ] Existing behavior, code and constraints inspected.
- [ ] Relevant upstream gstack skill used **if** installed; otherwise record "not run".
- [ ] Code implemented on a separate branch.
- [ ] Automated tests run (exact commands, pass/fail, environment).
- [ ] Security/secret checks run; credentials not exposed.
- [ ] Domain-specific verification run against real data when required.
- [ ] Before/after behavior, limitations, and rollback described.
- [ ] PR reviewed; merge/deploy is a separate gated action.

## Evidence report template
```markdown
Project:
Commit / PR:
Goal:
Implementation:
Tests (commands, outcome):
gstack skills actually executed (or not run):
Data source and timestamp:
Remaining risks:
Release decision: HOLD / READY
```

All numerical claims should identify the source and whether each figure is observed, derived, or hypothetical.
