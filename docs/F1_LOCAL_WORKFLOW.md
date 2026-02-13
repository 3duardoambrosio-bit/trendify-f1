# F1 Local Workflow (SYNAPSE / Trendify F1)

This repo enforces local gates via Git hooks:
- pre-commit: SYNAPSE F1 GATE (doctor + pytest)
- pre-push:   SYNAPSE F1 CONTROL TOWER (hook verify + gate + doctor + pytest + ruleset audit)

Quick commands (PowerShell):
1) Snapshot:
   git status -sb
   git rev-parse --short HEAD
   git config --get core.hooksPath

2) Verify hooks:
   powershell -NoProfile -ExecutionPolicy Bypass -File tools/verify_local_hooks_f1.ps1

3) Run Control Tower (authoritative):
   powershell -NoProfile -ExecutionPolicy Bypass -File tools/run_f1_control_tower.ps1

Notes:
- artifacts/ is intentionally ignored at repo-level (Control Tower writes report JSON there).
- .githooks/* is ignored except tracked hooks: pre-commit, pre-push.
- .gitattributes enforces LF for repo text; .cmd/.bat are CRLF.

If push fails:
- Read the Control Tower output; it prints the failing rule and ACCEPTANCE_OK=0.
- Fix the underlying issue, then rerun Control Tower locally before retrying push.

## PR Merge Rescue (resolve conversations)

If PR merge is BLOCKED by "A conversation must be resolved":

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/gh_pr_merge_resolve_threads.ps1 `
  -Owner "3duardoambrosio-bit" -Repo "trendify-f1" -Pr <PR_NUMBER> -MergeMethod squash -Admin -DeleteBranch
```
