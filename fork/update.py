#!/usr/bin/env python3
"""Merge an upstream revision and regenerate the fork metadata on a new branch."""

import argparse
import re
import subprocess
import tomllib

from prepare import CRATES, ROOT, git, prepare


def run(*args, check=True):
    return subprocess.run(args, cwd=ROOT, check=check)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("revision", help="upstream commit, tag, or branch")
    parser.add_argument("version", help="new shared fork version, for example 0.1.1")
    args = parser.parse_args()
    if not re.fullmatch(
        r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", args.version
    ):
        parser.error("version must have the form X.Y.Z")
    if git("status", "--porcelain").strip():
        parser.error("commit or stash local changes before the update")
    config_path = ROOT / "fork/config.toml"
    config_text = config_path.read_text()
    config = tomllib.loads(config_text)
    if tuple(map(int, args.version.split("."))) <= tuple(
        map(int, config["version"].split("."))
    ):
        parser.error("the new fork version must be greater than the current version")
    run("git", "fetch", "https://github.com/mstange/samply.git", args.revision)
    revision = git("rev-parse", "FETCH_HEAD^{commit}").strip()
    if run(
        "git", "merge-base", "--is-ancestor", config["upstream"], revision, check=False
    ).returncode:
        parser.error(
            "the new upstream revision must descend from the current upstream revision"
        )
    # Keep source edits out of this packaging-only fork.
    run("git", "diff", "--exit-code", config["upstream"], "--", "*.rs")
    run("git", "switch", "-c", f"sync/{args.version}-{revision[:12]}")
    result = run("git", "merge", "--no-commit", "--no-ff", revision, check=False)
    if result.returncode:
        conflicts = git("diff", "--name-only", "--diff-filter=U").splitlines()
        generated = {"Cargo.toml", "Cargo.lock", "README.md"}
        generated.update(
            f"{crate}/{name}"
            for crate in CRATES
            for name in ("Cargo.toml", "README.md", "LICENSE-MIT", "LICENSE-APACHE")
        )
        unexpected = [
            name
            for name in conflicts
            if name not in generated and not name.startswith(".github/workflows/")
        ]
        if unexpected or not conflicts:
            run("git", "merge", "--abort", check=False)
            raise SystemExit(
                f"Resolve the upstream merge manually: {unexpected or 'merge failed'}"
            )
        # prepare() reconstructs these files from the new upstream revision.
        if "Cargo.lock" in conflicts:
            run("git", "checkout", "--ours", "--", "Cargo.lock")
    config_text = config_text.replace(
        f'upstream = "{config["upstream"]}"', f'upstream = "{revision}"'
    )
    config_text = config_text.replace(
        f'version = "{config["version"]}"', f'version = "{args.version}"'
    )
    config_path.write_text(config_text)
    prepare()
    run("cargo", "check", "--workspace", "--all-features")
    run("git", "add", "-A")
    print(
        "Upstream update is staged. Review the diff, run the checks in FORK.md, and commit it."
    )


if __name__ == "__main__":
    main()
