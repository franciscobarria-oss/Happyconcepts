# Deploy

Environments (all on the Contabo VPS, `ssh deploy@erp.fbs-host.com`; repo /opt/frappe_docker):

| Site | Compose project | Role |
|---|---|---|
| erp.fbs-host.com (+ erp-test) | `erpnext` (owns nginx-proxy + acme) | old live system, hk10. Not touched by the rebuild until go-live. |
| erp-staging.fbs-host.com | `erpnext-staging` | old staging, hk15 |
| **hcl-erp.fbs-host.com** | `hcl-erp` (`~/gitops/hcl-erp.yaml` + `hcl-erp.env`, chmod 600) | rebuilt system. Up: `cd /opt/frappe_docker && docker compose -p hcl-erp --env-file ~/gitops/hcl-erp.env -f ~/gitops/hcl-erp.yaml up -d` |

The hcl-erp stack copies the staging pattern: own DB, Redis and volumes; only the frontend joins
`erpnext_default` so nginx-proxy can route it; backend/websocket use the aliases
`hcl-backend` / `hcl-websocket` so they never collide with production's `backend`.

Image: `build_image.sh <tag>` builds `hk/erpnext-hrms:<tag>` from versions.env + the app at that git tag.
The app is cloned from the private repo github.com/franciscobarria-oss/happyconcepts (the Frappe app inside is named `happy_kitchen`) with the server's read-only deploy key `~/.ssh/happyconcepts_deploy` (public half added under the repo's Settings > Deploy keys).

## hcl-erp setup wizard answers (run 2026-10-17, from the command line)
Company **Happy Concepts**, abbreviation **HK**, currency HKD, country Hong Kong, language English,
time zone Asia/Hong_Kong, chart of accounts "Standard with Numbers", fiscal year 1 Apr to 31 Mar
(2026-2027), dates dd-mm-yyyy, numbers #,###.##, currency precision 4, float precision 3.
Outgoing email muted (`mute_emails` in site_config) until go-live. Then `install-app happy_kitchen`
applies the base setup (setup/base.py).
