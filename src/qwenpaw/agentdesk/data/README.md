# Bundled AgentDesk seed catalog

This directory ships the **out-of-the-box** plaza cards (岗位智能体) and multi-agent teams (多智能体团队) that appear on a fresh install.

## Files

| File | Purpose |
|------|---------|
| `builtin_agents.json` | Versioned catalog of plaza cards and teams |

## When seed runs

On startup (`agentdesk app`), `maybe_seed_builtin_agents()` runs when **any** of these is true:

1. **Fresh store** — `plaza`, `employees`, and `teams` are all empty (typical first clone).
2. **Catalog upgrade** — `builtin_agents.json` `version` is greater than `store.meta.builtin_seed_version`.
3. **Explicit reseed** — environment variable `AGENTDESK_RESEED_BUILTINS=1`.

Otherwise seed is skipped so existing user data (including deletions) is preserved.

Seed logic is **additive and idempotent**: it inserts missing entries by `name` / team `id` and provisions `emp_*` agent profiles plus hidden team `lead_*` leaders. It does not overwrite user-edited plaza cards.

## What gets provisioned

For each auto-join plaza role:

- Plaza card in `store.json` → `plaza`
- Employee record → `employees`
- QwenPaw agent profile (`emp_<hash>`) with workspace `PROFILE.md`, skills, and bootstrap skipped

For each team in the catalog:

- Team record → `teams`
- Hidden leader agent (`lead_<teamId>`) via `team_leader_agents.py`
- Member employee agents ensured first

Avatars are generated on first access from deterministic DiceBear seeds (not stored in JSON).

## Updating bundled defaults

1. Edit your local AgentDesk instance until plaza/teams look right.
2. Export from your data directory:

   ```bash
   python scripts/export_agentdesk_builtin_seed.py \
     --store ~/.agentdesk/agentdesk/store.json \
     --out src/qwenpaw/agentdesk/data/builtin_agents.json
   ```

3. Bump `"version"` in `builtin_agents.json` when adding entries so existing installs receive the new cards on next startup.
4. Run tests:

   ```bash
   pytest tests/agentdesk/test_builtin_agents.py -v
   ```

## User deletions

When a user deletes a packaged plaza card or team, its `builtin_id` is recorded in `store.meta.dismissed_builtin_ids`. Dismissed entries are not re-seeded on restart or catalog upgrade unless `AGENTDESK_RESEED_BUILTINS=1`.

## JSON schema (informal)

```json
{
  "version": 1,
  "plaza": [
    {
      "builtin_id": "doc-master",
      "name": "文档大师",
      "tags": ["通用办公"],
      "desc": "…",
      "skills": ["docx", "pdf"],
      "auto_join": true
    },
    {
      "builtin_id": "account-opening-team-card",
      "name": "开户协同小队",
      "kind": "team",
      "team_id": "builtin-account-opening-team",
      "auto_join": false
    }
  ],
  "teams": [
    {
      "id": "builtin-account-opening-team",
      "name": "开户协同小队",
      "desc": "…",
      "members": ["SIM卡开通业务员", "5G套餐顾问"],
      "skills": ["multi_agent_collaboration"]
    }
  ]
}
```

- `auto_join: false` — plaza card only (team cards); employees are not auto-created from this entry.
- `kind: "team"` — marks a plaza card that links to a multi-agent team.
