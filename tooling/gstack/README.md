# Shared gstack integration starter (all projects)

This directory is a **portable starter kit**, not a copy of gstack and not an installed gstack runtime. It has no dependency on horse-racing code. Copy `tooling/gstack/` to another repository, or run the installer directly from a local checkout.

## Source and requirements
- Upstream: https://github.com/garrytan/gstack
- Installation and supported hosts: https://github.com/garrytan/gstack#other-ai-agents
- Installation prerequisites: https://github.com/garrytan/gstack/blob/main/docs/install.md
- gstack is MIT licensed. Review upstream changes before upgrading.
- Git, Bun (upstream recommends v1.4.2+), a supported coding-agent CLI and its account/session are required. A mobile ChatGPT session or GitHub connector **cannot execute** local gstack slash commands by itself.

## Local installation (Windows: WSL or compatible shell)
```bash
bash tooling/gstack/install.sh codex
# or for Claude Code:
bash tooling/gstack/install.sh claude
```

This installs upstream in `~/gstack` by default, unless `GSTACK_HOME` is set. Existing installations are never auto-upgraded. To upgrade, follow upstream's official release instructions and inspect the diffs first.

## Project-independent workflow

1. **Plan:** use upstream `gstack-office-hours` / `plan-eng-review` in the supported agent.
2. **Develop:** make changes in a feature branch; preserve existing project config.
3. **Review:** use `review`, `investigate`, and `test-audit` as applicable.
4. **Verify:** run the repository's actual tests, lint checks and domain-data validations. Never mark simulated data as a production result.
5. **Release:** open a PR and require test evidence and review before merging. Do not automatically deploy or push to main.

Skill invocation names depend on host; consult the current upstream README. These steps are **operating instructions**, not claims that skills run automatically in the GitHub connector.

## Use in any future repository
Copy `tooling/gstack/` and `tooling/gstack/PROJECT_CHECKLIST.md` into the new repository and run the installer once per developer environment (not once per repository). Add project-specific test commands to the checklist without coupling to a single application. For shared GitHub workflows, the new repository must install its own CI checks and grant the appropriate GitHub Actions permissions.

## Safety
No tokens/credentials committed. Never send `.env` to an external agent. No changes to model versions, production deployments, or main branch without real tests. This starter deliberately avoids modifying the existing repository's root AGENTS.md and any production forecast files.
