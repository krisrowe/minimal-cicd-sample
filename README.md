# Minimal CI/CD Sample

A minimal, self-contained GitHub Actions pipeline that validates Terraform and Helm against a real GCP project — no Apigee org or Kubernetes cluster required.

**What the pipeline validates on every push:**
- GCP authentication via SA key (proves credentials work end-to-end)
- `terraform init` + `plan` (validates provider config and GCP API access)
- `helm template` (validates chart rendering, no cluster needed)
- Structural checks via `scripts/check.py` (optional Apigee API probe, skips gracefully)

---

## Prerequisites

- [`gcloud` CLI](https://cloud.google.com/sdk/docs/install) — authenticated with an account that can create GCP projects
- [`gh` CLI](https://cli.github.com/) — authenticated to this GitHub repo
- [`terraform`](https://developer.hashicorp.com/terraform/install) >= 1.0
- [`helm`](https://helm.sh/docs/intro/install/) >= 3.0
- `python3` (stdlib only — no pip installs needed)

---

## Quick Start

### 1. Clone

```bash
git clone https://github.com/krisrowe/minimal-cicd-sample.git
cd minimal-cicd-sample
```

### 2. Initialize GCP (one-time, local only)

```bash
python3 scripts/init.py [project-id] [--billing-account BILLING_ID] [--github-repo OWNER/REPO]
```

**Project ID resolution** (in order):
1. CLI positional argument
2. Existing `sa-key.json` (idempotent re-run — no flags needed)
3. Auto-generated: `min-cicd-sample-<random>`

**`--billing-account` is required when creating a new project:**
```bash
gcloud billing accounts list   # find your billing account ID
python3 scripts/init.py --billing-account 010217-XXXXXX-XXXXXX
```

**Re-run (existing project):**
```bash
python3 scripts/init.py
```

This script (all steps idempotent):
1. Creates the GCP project
2. Links billing account
3. Resets SA key creation org policy at project level (best-effort)
4. Enables required APIs (`cloudresourcemanager`, `compute`, `apigee`, etc.)
5. Creates a `deployer` service account with Owner role
6. Exports SA key → `sa-key.json` (**gitignored — never committed**)
7. Pushes `GCP_SA_KEY` and `GCP_PROJECT_ID` to GitHub Actions secrets via `gh`

> If SA key creation is blocked by org policy and the reset fails, `init.py` automatically falls back to setting up **Workload Identity Federation** (keyless OIDC) instead.

### 3. Run locally

```bash
python3 scripts/deploy.py
```

Credential resolution (auto-detected):
| Context | Source |
|---|---|
| Local (key file) | `sa-key.json` → `GOOGLE_APPLICATION_CREDENTIALS` |
| Local (WIF/ADC) | `GCP_SA_EMAIL` env var → SA impersonation |
| CI (key file) | `GCP_SA_KEY` env var (JSON string) |
| CI (WIF) | Ambient credentials from `google-github-actions/auth` |

### 4. Push to trigger CI

```bash
git push origin main
```

GitHub Actions runs `.github/workflows/verify.yml` using the secrets set in step 2.

---

## Repository Structure

```
terraform/          Terraform config (google provider, reads project metadata)
helm/               Helm chart (lint + template only — no cluster needed)
scripts/
  init.py           LOCAL ONLY: GCP project setup + GitHub secret push
  deploy.py         Local + CI: GCP validation, Terraform plan, Helm, checks
  check.py          Structural checks + optional Apigee API probe (graceful skip)
.github/
  workflows/
    verify.yml      GitHub Actions pipeline
.gitignore          Excludes sa-key.json and Terraform cache
sa-key.json         SA credentials — gitignored, local only
```

## Notes

- No Apigee org required — `check.py` skips the Apigee probe gracefully on 403/404
- No Kubernetes cluster required — Helm runs client-side only (`helm template`)
- Terraform runs `plan` only — no infrastructure is created or modified
- `sa-key.json` is gitignored and never committed
