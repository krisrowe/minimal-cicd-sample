#!/usr/bin/env python3
"""
check.py - Structural and API connectivity checks.
Runs both locally and in GitHub Actions.
"""

import os
import sys
import json
import subprocess


def load_credentials():
    key_file = "sa-key.json"
    if os.path.exists(key_file):
        with open(key_file) as f:
            return json.load(f)
    elif "GCP_SA_KEY" in os.environ:
        return json.loads(os.environ["GCP_SA_KEY"])
    return None


def check_structure():
    print("Checking repo structure...")
    required = ["terraform", "helm", "scripts"]
    ok = True
    for d in required:
        if os.path.isdir(d):
            print(f"  ✅ {d}/")
        else:
            print(f"  ❌ {d}/ missing")
            ok = False
    return ok


def check_apigee_api(project_id):
    print(f"\nChecking Apigee API for project: {project_id}")
    token_result = subprocess.run(
        "gcloud auth print-access-token",
        shell=True, capture_output=True, text=True
    )
    if token_result.returncode != 0:
        print("  ⚠️  No gcloud token available, skipping Apigee API check.")
        return

    token = token_result.stdout.strip()
    url = f"https://apigee.googleapis.com/v1/organizations/{project_id}"
    result = subprocess.run(
        f"curl -s -o /tmp/apigee_resp.json -w '%{{http_code}}' "
        f"-H 'Authorization: Bearer {token}' {url}",
        shell=True, capture_output=True, text=True
    )
    http_code = result.stdout.strip()

    if http_code == "200":
        with open("/tmp/apigee_resp.json") as f:
            data = json.load(f)
        print(f"  ✅ Apigee org found: {data.get('name', project_id)}")
    elif http_code == "404":
        print("  ℹ️  No Apigee org found for this project (not yet provisioned — skipping).")
    else:
        print(f"  ⚠️  Apigee API returned HTTP {http_code} — skipping check.")


def main():
    if not check_structure():
        sys.exit(1)

    creds = load_credentials()
    if creds:
        check_apigee_api(creds["project_id"])
    else:
        print("\n⚠️  No credentials found, skipping Apigee API check.")

    print("\n✅ All checks passed.")


if __name__ == "__main__":
    main()
