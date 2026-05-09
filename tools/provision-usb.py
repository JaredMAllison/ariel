#!/usr/bin/env python3
"""
provision-usb.py — LMF USB Provisioning Tool

Generates a personalized LMF instance on a USB drive for any target user.
Handles dependency downloads, vault personalization, and config generation.

Usage:
    python provision-usb.py --target Jason
    python provision-usb.py --target Jason --vault-name "Jedi_Archives" --ai-name "Ariel"
    python provision-usb.py --interactive       # ask everything

Can be re-run to update personalization without re-downloading deps.
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None


# --- Configuration -----------------------------------------------------------

PYTHON_VERSION = "3.12.10"
PYTHON_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
GETPIP_URL = "https://bootstrap.pypa.io/get-pip.py"

OLLAMA_VERSION = "v0.23.2"
OLLAMA_URL = f"https://github.com/ollama/ollama/releases/download/{OLLAMA_VERSION}/ollama-windows-amd64.zip"


# --- File templates ----------------------------------------------------------

ARIEL_MD_TEMPLATE = """---
title: Assistant Identity
type: identity
---

You are the personal LMF assistant for {target_name}.
You have access to their knowledge vault.

You help manage tasks, projects, and notes. You can search the vault,
read notes, and with operator confirmation, create or update notes.

Be concise. Ask before writing. Confirm before deleting anything.
"""

MEMORY_MD_TEMPLATE = """# Memory Index — {target_name}

(No memories yet — memories will appear here as you use the assistant.)
"""

INBOX_MD_CONTENT = """# Inbox — {target_name}

Raw capture buffer. Add notes here for the assistant to process.
"""

LOCAL_MD_CONTENT = """# Welcome to LMF, {target_name}

This is your personal cognitive prosthetic — your Local Mind Foundation instance.
Everything here belongs to you. Your vault, your assistant, your space.

To get started:
- Open the AI chat panel to talk to {ai_name}
- Use Inbox.md to capture thoughts
- Your assistant will help you set up tasks and projects

The system comes to you.
"""

DEPLOY_YAML_TEMPLATE = """instance_name: "{instance_name}"
trust_profile: {trust_profile}
onboarding_mode: {onboarding_mode}
"""

APP_CONFIG_JS_TEMPLATE = """window.APP_CONFIG = {{
  vaultName: {vault_name!r},
  aiName: {ai_name!r},
}};
"""


# --- Helpers -----------------------------------------------------------------

def detect_os():
    system = platform.system()
    if system == "Windows":
        return {"sep": "\\", "default_root": Path(os.environ.get("USERPROFILE", "C:\\Users\\Default"))}
    return {"sep": "/", "default_root": Path.home()}


def step(msg):
    print(f"\n=== {msg} ===")


def prompt(label, default=None):
    default_str = f" [{default}]" if default else ""
    val = input(f"  {label}{default_str}: ").strip()
    return val if val else (default or "")


def choice(label, options, default):
    joined = "/".join(options)
    val = input(f"  {label} ({joined}) [{default}]: ").strip().lower()
    return val if val in options else default


def download_file(url, dest, label):
    """Download a file, showing status."""
    dest = Path(dest)
    if dest.exists():
        print(f"  {label} already exists — skipping")
        return True
    print(f"  Downloading {label}...")
    print(f"    {url}")
    try:
        import requests
        r = requests.get(url, stream=True, timeout=30)
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)
                if total and total > 10 * 1024 * 1024:
                    pct = downloaded * 100 // total
                    print(f"    {pct}% ({downloaded // 1024 // 1024} MB / {total // 1024 // 1024} MB)", end="\r")
        print(f"    OK — {dest.name} ({dest.stat().st_size // 1024 // 1024} MB)")
        return True
    except Exception as e:
        print(f"    FAILED: {e}")
        return False


def extract_zip(zip_path, target_file, output_dir):
    """Extract a single file from a ZIP archive."""
    import zipfile
    zip_path = Path(zip_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as z:
        for info in z.infolist():
            if info.filename.endswith(target_file):
                out_path = output_dir / Path(info.filename).name
                with z.open(info) as src, open(out_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                print(f"    Extracted {target_file} ({out_path.stat().st_size // 1024 // 1024} MB)")
                return True
    print(f"    {target_file} not found in archive")
    return False


# --- Provisioning ------------------------------------------------------------

def provision(usb_path, target_name, vault_name, ai_name, instance_name,
              trust_profile, onboarding_mode, skip_downloads):
    usb = Path(usb_path)
    if not usb.is_dir():
        print(f"ERROR: {usb_path} is not a directory or doesn't exist")
        sys.exit(1)

    print(f"\n  Target:     {target_name}")
    print(f"  Vault name: {vault_name}")
    print(f"  AI name:    {ai_name}")
    print(f"  Instance:   {instance_name}")
    print(f"  Trust:      {trust_profile}")
    print(f"  Onboarding: {onboarding_mode}")
    print(f"  USB path:   {usb}")
    print()

    # --- Download dependencies -----------------------------------------------

    if not skip_downloads:
        step("Downloading Python embeddable")
        python_zip = usb / "python" / f"python-{PYTHON_VERSION}-embed-amd64.zip"
        python_exe = usb / "python" / "python.exe"
        if not python_exe.exists():
            if download_file(PYTHON_URL, python_zip, "Python embeddable"):
                import zipfile
                with zipfile.ZipFile(python_zip, "r") as z:
                    z.extractall(usb / "python")
                print(f"    Extracted to python/")
        else:
            print("  Python already present")

        step("Downloading get-pip.py")
        download_file(GETPIP_URL, usb / "python" / "get-pip.py", "get-pip.py")

        step("Downloading Ollama")
        ollama_zip = usb / "ollama" / "ollama-windows-amd64.zip"
        ollama_exe = usb / "ollama" / "ollama.exe"
        if not ollama_exe.exists():
            if download_file(OLLAMA_URL, ollama_zip, "Ollama"):
                extract_zip(ollama_zip, "ollama.exe", usb / "ollama")
        else:
            print("  Ollama already present")
    else:
        print("Skipping dependency downloads (--skip-downloads)")
        print("  Make sure python/, ollama/ollama.exe, and python/get-pip.py exist.")

    # --- Create vault structure ----------------------------------------------

    step("Setting up vault")
    vault = usb / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    (vault / "Tasks").mkdir(exist_ok=True)
    (vault / "Projects").mkdir(exist_ok=True)
    (vault / "Daily").mkdir(exist_ok=True)
    (vault / "System").mkdir(exist_ok=True)
    (vault / "System" / "Memory").mkdir(parents=True, exist_ok=True)
    (vault / "System" / "Skills").mkdir(exist_ok=True)

    # Write personalized files
    (vault / "Inbox.md").write_text(INBOX_MD_CONTENT.format(target_name=target_name), encoding="utf-8")
    (vault / "System" / "Memory" / "ARIEL.md").write_text(
        ARIEL_MD_TEMPLATE.format(target_name=target_name), encoding="utf-8")
    (vault / "System" / "Memory" / "MEMORY.md").write_text(
        MEMORY_MD_TEMPLATE.format(target_name=target_name), encoding="utf-8")

    # --- Generate configs ----------------------------------------------------

    step("Generating configs")

    # app-config.js
    cockpit_dir = usb / "cockpit"
    cockpit_dir.mkdir(parents=True, exist_ok=True)
    (cockpit_dir / "app-config.js").write_text(
        APP_CONFIG_JS_TEMPLATE.format(vault_name=vault_name, ai_name=ai_name), encoding="utf-8")

    # deploy.yaml
    lmf_operator = usb / "lmf" / "operator"
    lmf_operator.mkdir(parents=True, exist_ok=True)
    (lmf_operator / "deploy.yaml").write_text(
        DEPLOY_YAML_TEMPLATE.format(
            instance_name=instance_name,
            trust_profile=trust_profile,
            onboarding_mode=onboarding_mode,
        ),
        encoding="utf-8",
    )

    # --- Disk usage summary --------------------------------------------------

    total_mb = sum(f.stat().st_size for f in usb.rglob("*") if f.is_file()) // (1024 * 1024)
    free_mb = shutil.disk_usage(usb).free // (1024 * 1024)

    step("Summary")
    print(f"  USB size:      {total_mb} MB used, {free_mb} MB free")
    print(f"  Python:        {'✓' if (usb/'python'/'python.exe').exists() else '✗'}")
    print(f"  get-pip.py:    {'✓' if (usb/'python'/'get-pip.py').exists() else '✗'}")
    print(f"  ollama.exe:    {'✓' if (usb/'ollama'/'ollama.exe').exists() else '✗'}")
    print(f"  Vault:         {target_name}'s vault ready")
    print(f"  Config:        {instance_name} / {ai_name}")
    print()

    print("  Ship it! On the target machine:")
    print("    1. Plug in USB")
    print("    2. Double-click setup.bat")
    print("    3. Answer the setup wizard questions")
    print("    4. Double-click pull-models.bat (downloads AI model ~5 GB)")
    print("    5. Double-click 'LMF' desktop shortcut")
    print()


# --- CLI ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Provision a LMF USB drive for a target user",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python provision-usb.py --target Jason --usb F:
  python provision-usb.py --target Alex --vault-name "Workshop" --ai-name "Athena"
  python provision-usb.py --interactive
        """,
    )
    parser.add_argument("--target", "-t", help="Target user's name")
    parser.add_argument("--usb", "-u", help="USB drive path (default: current directory)")
    parser.add_argument("--vault-name", default=None, help="Display name for the vault")
    parser.add_argument("--ai-name", default=None, help="Name for the AI assistant")
    parser.add_argument("--instance", default=None, help="Instance name (default: LMF)")
    parser.add_argument("--trust-profile", choices=["personal", "professional", "mixed"], default="personal")
    parser.add_argument("--onboarding-mode", choices=["guided", "quick", "skip"], default="guided")
    parser.add_argument("--interactive", "-i", action="store_true", help="Ask for all values interactively")
    parser.add_argument("--skip-downloads", action="store_true",
                        help="Skip downloading deps (use if already downloaded)")

    args = parser.parse_args()

    usb_path = args.usb or os.getcwd()

    if args.interactive or not args.target:
        print("=== LMF USB Provisioning ===\n")
        target_name = prompt("Who is this for", args.target)
        vault_name = prompt("Vault display name", args.vault_name or "Jedi_Archives")
        ai_name = prompt("AI assistant name", args.ai_name or "Ariel")
        instance_name = prompt("Instance name", args.instance or "LMF")
        trust_profile = choice("Trust profile", ["personal", "professional", "mixed"], args.trust_profile)
        onboarding_mode = choice("Onboarding mode", ["guided", "quick", "skip"], args.onboarding_mode)
        skip = args.skip_downloads or (input("Skip dependency downloads? (y/N): ").strip().lower() == "y")
    else:
        target_name = args.target
        vault_name = args.vault_name or f"{target_name}'s LMF"
        ai_name = args.ai_name or "Ariel"
        instance_name = args.instance or "LMF"
        trust_profile = args.trust_profile
        onboarding_mode = args.onboarding_mode
        skip = args.skip_downloads

    if not target_name:
        print("ERROR: --target is required in non-interactive mode")
        sys.exit(1)

    provision(usb_path, target_name, vault_name, ai_name, instance_name,
              trust_profile, onboarding_mode, skip)


if __name__ == "__main__":
    main()
