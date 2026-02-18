#!/usr/bin/env python3
"""
deploy.py - Runs Terraform and Helm. Works locally and in GitHub Actions.

Credential resolution:
  Local (key file):   sa-key.json present → GOOGLE_APPLICATION_CREDENTIALS
  Local (WIF/ADC):    GCP_SA_EMAIL set → GOOGLE_IMPERSONATE_SERVICE_ACCOUNT via ADC
  CI (key file):      GCP_SA_KEY env var (JSON string) → written to temp file
  CI (WIF):           Already authenticated by google-github-actions/auth step

GCP_PROJECT_ID must always be set (env var or extracted from key JSON).
"""

import json
import os
import subprocess
import sys
import tempfile


def run(cmd, env=None):
    print(f"  $ {cmd}")
    subprocess.run(cmd, shell=True, check=True, env=env or os.environ.copy())


def setup_credentials():
    """Returns (env dict, tmp_key_path or None). Caller must clean up tmp_key_path."""
    env = os.environ.copy()
    tmp_key_path = None

    # Option 1: local sa-key.json
    if os.path.exists("sa-key.json"):
        print("Auth: using local sa-key.json")
        with open("sa-key.json") as f:
            creds = json.load(f)
        env["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.abspath("sa-key.json")
        env.setdefault("GCP_PROJECT_ID", creds["project_id"])

    # Option 2: CI GCP_SA_KEY env var (JSON string)
    elif "GCP_SA_KEY" in os.environ:
        print("Auth: using GCP_SA_KEY env var (key file mode)")
        creds = json.loads(os.environ["GCP_SA_KEY"])
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump(creds, tmp)
        tmp.close()
        tmp_key_path = tmp.name
        env["GOOGLE_APPLICATION_CREDENTIALS"] = tmp_key_path
        env.setdefault("GCP_PROJECT_ID", creds["project_id"])

    # Option 3: WIF (already authed by workflow) or ADC + impersonation
    elif "GCP_SA_EMAIL" in os.environ:
        print(f"Auth: ADC + impersonating {os.environ['GCP_SA_EMAIL']}")
        env["GOOGLE_IMPERSONATE_SERVICE_ACCOUNT"] = os.environ["GCP_SA_EMAIL"]

    # Option 4: WIF in CI — already authenticated, nothing to set
    else:
        print("Auth: using ambient credentials (WIF or ADC)")

    return env, tmp_key_path


def get_project_id(env):
    project_id = env.get("GCP_PROJECT_ID") or os.environ.get("GCP_PROJECT_ID")
    if not project_id:
        print("ERROR: GCP_PROJECT_ID not set.")
        print("  Set it with: export GCP_PROJECT_ID=<your-project-id>")
        sys.exit(1)
    return project_id


def main():
    env, tmp_key_path = setup_credentials()
    project_id = get_project_id(env)
    env["GCP_PROJECT_ID"] = project_id
    env["GOOGLE_PROJECT"] = project_id

    print(f"Project ID: {project_id}")

    try:
        # Validate GCP access
        print("\n--- GCP Access Validation ---")
        run(f"gcloud projects describe {project_id} --format='value(name)'", env=env)

        # Terraform (plan only)
        print("\n--- Terraform ---")
        run("terraform -chdir=terraform init", env=env)
        run(f"terraform -chdir=terraform plan -var='project_id={project_id}'", env=env)

        # Helm (template only — no cluster needed)
        print("\n--- Helm ---")
        run(f"helm template minimal-demo ./helm --set projectId={project_id}")

        # Structural + Apigee API check
        print("\n--- Checks ---")
        run("python3 scripts/check.py", env=env)

    finally:
        if tmp_key_path:
            os.unlink(tmp_key_path)

    print("\n✅ Deploy complete.")


if __name__ == "__main__":
    main()
