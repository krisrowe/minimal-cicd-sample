# Minimal CI/CD Sample

Demonstrates a GitHub Actions CI/CD pipeline that validates Terraform and Helm against a real GCP project — no Apigee org or Kubernetes cluster required. Authentication uses **Workload Identity Federation** (keyless — no SA JSON keys).

## Prerequisites

Install locally:
- [`gcloud` CLI](https://cloud.google.com/sdk/docs/install) — authenticated with an account that can create GCP projects
- [`gh` CLI](https://cli.github.com/) — authenticated to this GitHub repo
- [`terraform`](https://developer.hashicorp.com/terraform/install) >= 1.0
- [`helm`](https://helm.sh/docs/intro/install/) >= 3.0
- `python3` (stdlib only — no pip installs needed)

---

## Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/krisrowe/minimal-cicd-sample.git
cd minimal-cicd-sample
```

### 2. Initialize GCP infrastructure (local, one-time)

```bash
python3 scripts/init.py [project-id] [--billing-account BILLING_ID] [--github-repo OWNER/REPO]
```

**Project ID resolution** (in order):
1. CLI positional argument
2. Auto-generated: `min-cicd-sample-<random>`

**`--billing-account` is required when creating a new project.** Find yours with:
```bash
gcloud billing accounts list
```

**Example (new project):**
```bash
python3 scripts/init.py --billing-account 010217-XXXXXX-XXXXXX
```

**Example (existing project, re-run):**
```bash
python3 scripts/init.py my-project-id
```

This script (all steps idempotent):
1. Creates the GCP project
2. Links billing account
3. Enables required APIs (`iamcredentials`, `compute`, `apigee`)
4. Creates a `deployer` service account with Owner role
5. Creates a Workload Identity Pool + GitHub OIDC Provider
6. Grants the SA impersonation rights to the GitHub repo
7. Pushes `WIF_PROVIDER`, `WIF_SA_EMAIL`, `GCP_PROJECT_ID` to GitHub Actions secrets via `gh`

> **No SA JSON key is created.** GitHub Actions authenticates via OIDC tokens (keyless).

### 3. Authenticate locally (one-time)

```bash
gcloud auth application-default login
export GCP_PROJECT_ID=<your-project-id>
```

### 4. Run locally

```bash
python3 scripts/deploy.py
```

Runs (using your local ADC credentials):
- `gcloud projects describe` — validates GCP access
- `terraform init` + `plan` (plan-only — no infrastructure changes)
- `helm template` (dry-run, no cluster needed)
- `scripts/check.py` (structural checks + optional Apigee API probe)

### 5. Push and trigger CI

```bash
git add .
git commit -m "initial"
git push origin main
```

GitHub Actions runs `.github/workflows/verify.yml` automatically using the WIF secrets set in step 2.

---

## How It Works

### Authentication

| Context | Method |
|---|---|
| Local | Application Default Credentials (`gcloud auth application-default login`) |
| GitHub Actions | Workload Identity Federation (OIDC, keyless) |

### No SA JSON Keys

Authentication uses Workload Identity Federation — GitHub Actions presents a short-lived OIDC token that GCP exchanges for temporary credentials. No long-lived keys are stored anywhere.

### No Apigee Org Required

`check.py` probes the Apigee API but **skips gracefully** (no failure) if no org exists.

### No Kubernetes Cluster Required

Helm uses `helm lint` and `helm template` — client-side only, no cluster connection needed.

---

## Repository Structure

```
terraform/          Terraform config (google provider, validates project access)
helm/               Helm chart (lint + template only)
scripts/
  init.py           LOCAL ONLY: GCP setup + WIF + GitHub secret push
  deploy.py         Local + CI: GCP validation, Terraform plan, Helm, checks
  check.py          Structural checks + optional Apigee API probe
.github/
  workflows/
    verify.yml      GitHub Actions pipeline (WIF auth)
.gitignore          Excludes Terraform cache; no SA key to worry about
```
