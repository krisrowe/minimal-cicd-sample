#!/usr/bin/env python3
"""
init.py - LOCAL ONLY. Idempotent GCP project setup.

Tries to export a SA JSON key (simplest). If org policy blocks key creation,
falls back to setting up Workload Identity Federation (keyless OIDC).

Usage:
    python3 scripts/init.py [project-id] [--billing-account BILLING_ID] [--github-repo OWNER/REPO]

Project ID resolution (in order):
  1. CLI positional argument
  2. Existing sa-key.json (idempotent re-run)
  3. Auto-generated: min-cicd-sample-<random6chars>

--billing-account is required when creating a new project.
--github-repo defaults to krisrowe/minimal-cicd-sample (used for WIF fallback).
"""

import argparse
import json
import os
import random
import string
import subprocess
import sys


GITHUB_REPO_DEFAULT = "krisrowe/minimal-cicd-sample"
POOL_ID = "github-pool"
PROVIDER_ID = "github-provider"
KEY_FILE = "sa-key.json"


def run(cmd, check=True, capture=False):
    kwargs = dict(shell=True, check=check)
    if capture:
        kwargs.update(capture_output=True, text=True)
    result = subprocess.run(cmd, **kwargs)
    return result.stdout.strip() if capture else None


def exists(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True).returncode == 0


def resolve_project_id(args):
    if args.project_id:
        print(f"Using project ID from argument: {args.project_id}")
        return args.project_id
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE) as f:
            data = json.load(f)
        project_id = data.get("project_id")
        if project_id:
            print(f"Using project ID from existing {KEY_FILE}: {project_id}")
            return project_id
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    project_id = f"min-cicd-sample-{suffix}"
    print(f"Auto-generated project ID: {project_id}")
    return project_id


def setup_wif(project_id, sa_email, github_repo):
    """Set up Workload Identity Federation as fallback when key creation is blocked."""
    print("\n  Falling back to Workload Identity Federation (keyless)...")

    # Create WIF pool (idempotent)
    if exists(f"gcloud iam workload-identity-pools describe {POOL_ID} --location=global --project {project_id}"):
        print(f"  ✅ WIF Pool '{POOL_ID}' already exists.")
    else:
        print(f"  Creating WIF Pool '{POOL_ID}'...")
        run(f'gcloud iam workload-identity-pools create {POOL_ID} '
            f'--location=global --display-name="GitHub Actions Pool" --project {project_id}')

    # Create WIF provider (idempotent)
    if exists(f"gcloud iam workload-identity-pools providers describe {PROVIDER_ID} "
              f"--workload-identity-pool={POOL_ID} --location=global --project {project_id}"):
        print(f"  ✅ WIF Provider '{PROVIDER_ID}' already exists.")
    else:
        print(f"  Creating WIF Provider '{PROVIDER_ID}'...")
        run(f'gcloud iam workload-identity-pools providers create-oidc {PROVIDER_ID} '
            f'--workload-identity-pool={POOL_ID} --location=global '
            f'--issuer-uri="https://token.actions.githubusercontent.com" '
            f'--attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" '
            f'--attribute-condition="attribute.repository==\\"{github_repo}\\"" '
            f'--project {project_id}')

    # Grant SA impersonation
    print("  Granting SA impersonation to WIF provider...")
    project_number = run(
        f"gcloud projects describe {project_id} --format='value(projectNumber)'", capture=True)
    wif_member = (f"principalSet://iam.googleapis.com/projects/{project_number}"
                  f"/locations/global/workloadIdentityPools/{POOL_ID}"
                  f"/attribute.repository/{github_repo}")
    run(f"gcloud iam service-accounts add-iam-policy-binding {sa_email} "
        f"--role='roles/iam.workloadIdentityUser' --member='{wif_member}' --project {project_id}")

    # Get full provider resource name
    full_provider = run(
        f"gcloud iam workload-identity-pools providers describe {PROVIDER_ID} "
        f"--workload-identity-pool={POOL_ID} --location=global --project {project_id} "
        f"--format='value(name)'", capture=True)

    # Push WIF secrets to GitHub
    print("  Pushing WIF secrets to GitHub...")
    run(f"gh secret set WIF_PROVIDER --body '{full_provider}'")
    run(f"gh secret set WIF_SA_EMAIL --body '{sa_email}'")
    run(f"gh secret set GCP_PROJECT_ID --body '{project_id}'")
    print("  ✅ WIF setup complete. GitHub secrets: WIF_PROVIDER, WIF_SA_EMAIL, GCP_PROJECT_ID")


def main():
    parser = argparse.ArgumentParser(description="Initialize GCP project for CI/CD demo.")
    parser.add_argument("project_id", nargs="?", help="GCP project ID (optional)")
    parser.add_argument("--billing-account", help="Billing account ID (required for new projects)")
    parser.add_argument("--github-repo", default=GITHUB_REPO_DEFAULT,
                        help=f"GitHub repo owner/name for WIF fallback. Default: {GITHUB_REPO_DEFAULT}")
    args = parser.parse_args()

    project_id = resolve_project_id(args)
    sa_name = "deployer"
    sa_email = f"{sa_name}@{project_id}.iam.gserviceaccount.com"
    github_repo = args.github_repo

    print(f"\nInitializing project: {project_id}")

    # 1. Create project (idempotent)
    if exists(f"gcloud projects describe {project_id}"):
        print("  ✅ Project already exists, skipping creation.")
    else:
        if not args.billing_account:
            print("ERROR: --billing-account is required when creating a new project.")
            print("  Find yours with: gcloud billing accounts list")
            sys.exit(1)
        print(f"  Creating project {project_id}...")
        run(f'gcloud projects create {project_id} --name="Minimal CICD Demo"')

    # 2. Link billing (if provided)
    if args.billing_account:
        print("  Linking billing account...")
        run(f"gcloud billing projects link {project_id} --billing-account={args.billing_account}")

    # 3. Reset SA key creation org policy (best-effort — may be blocked by org admin role)
    print("  Attempting to reset SA key creation policy (best-effort)...")
    reset_ok = subprocess.run(
        f"gcloud org-policies reset constraints/iam.disableServiceAccountKeyCreation --project {project_id}",
        shell=True, capture_output=True
    ).returncode == 0
    if reset_ok:
        print("  ✅ SA key creation policy reset.")
    else:
        print("  ⚠️  Could not reset SA key policy — will try key creation anyway, may fall back to WIF.")

    # 4. Enable APIs
    print("  Enabling APIs...")
    run(f"gcloud services enable cloudresourcemanager.googleapis.com iamcredentials.googleapis.com "
        f"orgpolicy.googleapis.com compute.googleapis.com apigee.googleapis.com --project {project_id}")

    # 5. Create SA (idempotent)
    if exists(f"gcloud iam service-accounts describe {sa_email} --project {project_id}"):
        print("  ✅ Service account already exists.")
    else:
        print(f"  Creating service account {sa_name}...")
        run(f'gcloud iam service-accounts create {sa_name} --display-name="Deployer SA" --project {project_id}')

    # 6. Grant Owner role
    print("  Granting Owner role...")
    run(f"gcloud projects add-iam-policy-binding {project_id} "
        f"--member='serviceAccount:{sa_email}' --role='roles/owner'")

    # 7. Try SA key export; fall back to WIF if blocked
    print(f"  Exporting SA key to {KEY_FILE}...")
    key_result = subprocess.run(
        f"gcloud iam service-accounts keys create {KEY_FILE} "
        f"--iam-account={sa_email} --project {project_id}",
        shell=True, capture_output=True
    )
    if key_result.returncode == 0:
        print(f"  ✅ SA key saved to {KEY_FILE} (gitignored).")
        # Push key as GitHub secret
        print("  Pushing GCP_SA_KEY to GitHub...")
        run(f"gh secret set GCP_SA_KEY < {KEY_FILE}")
        run(f"gh secret set GCP_PROJECT_ID --body '{project_id}'")
        print("\n✅ Done (key file mode).")
        print(f"   {KEY_FILE} saved locally (gitignored).")
        print(f"   GitHub secrets set: GCP_SA_KEY, GCP_PROJECT_ID")
    else:
        print("  ⚠️  Key creation blocked — setting up Workload Identity Federation instead.")
        setup_wif(project_id, sa_email, github_repo)
        print("\n✅ Done (WIF mode — no key file).")
        print("   For local runs: gcloud auth application-default login")
        print(f"   export GCP_PROJECT_ID={project_id}")
        print(f"   export GCP_SA_EMAIL={sa_email}")


if __name__ == "__main__":
    main()
