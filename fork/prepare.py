#!/usr/bin/env python3
"""Apply the registry metadata to the pinned upstream manifests."""

import argparse
import json
import re
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CRATES = (
    "samply-debugid",
    "samply-object",
    "samply-symbols",
    "samply-api",
    "wholesym",
)


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True)


def upstream_file(revision, path):
    return git("show", f"{revision}:{path}")


def set_package_value(manifest, key, value):
    section = re.search(r"(?ms)^\[package\]\n.*?(?=^\[|\Z)", manifest)
    if section is None:
        raise ValueError("upstream manifest has no package section")
    updated, count = re.subn(
        rf"(?m)^{re.escape(key)} = .*?$", f"{key} = {json.dumps(value)}", section[0]
    )
    if count != 1:
        raise ValueError(f"expected one package {key}, found {count}")
    return manifest[: section.start()] + updated + manifest[section.end() :]


def generated_files(config):
    revision, version = config["upstream"], config["version"]
    repository = config["repository"]
    root_manifest = upstream_file(revision, "Cargo.toml")
    workspace = tomllib.loads(root_manifest)["workspace"]
    excluded = sorted(
        set(workspace["members"]) - set(CRATES) | set(workspace.get("exclude", []))
    )
    replacement = (
        "# Modified for the Stackpulse fork: publish only the symbol libraries.\n"
        '[workspace]\nresolver = "2"\n'
        f"members = {json.dumps(CRATES)}\n"
        f"default-members = {json.dumps(CRATES)}\n"
        f"exclude = {json.dumps(excluded)}\n\n"
    )
    yield (
        "Cargo.toml",
        re.sub(
            r"(?ms)^\[workspace\]\n.*?(?=^\[|\Z)", replacement, root_manifest, count=1
        ),
    )
    notice = (
        f"Stackpulse fork of [mstange/samply](https://github.com/mstange/samply) at `{revision}`.\n"
        "The Rust source and API names are unchanged. The registry names use the `-stackpulse` suffix.\n"
        f"See [fork maintenance]({repository}/blob/main/FORK.md).\n\n---\n\n"
    )
    yield (
        "README.md",
        "# Wholesym for Stackpulse\n\n" + notice + upstream_file(revision, "README.md"),
    )
    for crate in CRATES:
        original = upstream_file(revision, f"{crate}/Cargo.toml")
        metadata = tomllib.loads(original)
        manifest = set_package_value(original, "name", f"{crate}-stackpulse")
        manifest = set_package_value(manifest, "version", version)
        manifest = set_package_value(manifest, "repository", repository)
        manifest = set_package_value(
            manifest,
            "description",
            metadata["package"]["description"] + " (Stackpulse fork)",
        )
        if "homepage" in metadata["package"]:
            manifest = set_package_value(manifest, "homepage", repository)
        for dependency in CRATES:
            pattern = rf"(?m)^({re.escape(dependency)}\s*=\s*\{{)([^\n]+)(\}})\s*$"

            def rename(match):
                fields, count = re.subn(
                    r'version\s*=\s*"[^"]+"', f'version = "={version}"', match[2]
                )
                if count != 1 or "path" not in fields or "package" in fields:
                    raise ValueError(f"unsupported upstream dependency: {match[0]}")
                return (
                    f'{match[1]} package = "{dependency}-stackpulse",{fields}{match[3]}'
                )

            manifest = re.sub(pattern, rename, manifest)
        if "lib" in metadata:
            raise ValueError(f"review the new upstream lib section in {crate}")
        manifest += f'\n[lib]\nname = "{crate.replace("-", "_")}"\n'
        yield (
            f"{crate}/Cargo.toml",
            "# Modified for the Stackpulse fork: package metadata and dependency aliases.\n"
            + manifest,
        )
        yield (
            f"{crate}/README.md",
            notice + upstream_file(revision, f"{crate}/README.md"),
        )
        for license_name in ("LICENSE-MIT", "LICENSE-APACHE"):
            path = f"{crate}/{license_name}"
            exists = (
                subprocess.run(
                    ["git", "cat-file", "-e", f"{revision}:{path}"],
                    cwd=ROOT,
                    capture_output=True,
                ).returncode
                == 0
            )
            yield path, upstream_file(revision, path if exists else license_name)


def prepare(check=False):
    config = tomllib.loads((ROOT / "fork/config.toml").read_text())
    expected = dict(generated_files(config))
    for name, content in expected.items():
        path = ROOT / name
        if check:
            if not path.exists() or path.read_text() != content:
                raise SystemExit(f"Regenerate {name} with python3 fork/prepare.py")
        else:
            path.write_text(content)
    # Upstream workflows build and release the samply application, outside this fork's workspace.
    workflows = git(
        "ls-tree", "-r", "--name-only", config["upstream"], ".github/workflows"
    ).splitlines()
    for name in workflows:
        if name == ".github/workflows/fork.yml":
            raise SystemExit(
                "Upstream now owns fork.yml. Resolve the workflow name before the update."
            )
        if check and (ROOT / name).exists():
            raise SystemExit(f"Upstream application workflow remains: {name}")
        if not check:
            (ROOT / name).unlink(missing_ok=True)
    # A new upstream path dependency must not silently resolve to an unrelated registry package.
    for crate in CRATES:
        manifest = tomllib.loads(expected[f"{crate}/Cargo.toml"])
        tables = [manifest] + list(manifest.get("target", {}).values())
        for table in tables:
            for kind in ("dependencies", "build-dependencies", "dev-dependencies"):
                for name, dep in table.get(kind, {}).items():
                    if isinstance(dep, dict) and "path" in dep:
                        if (
                            name not in CRATES
                            or dep.get("package") != f"{name}-stackpulse"
                            or dep.get("version") != f"={config['version']}"
                        ):
                            raise SystemExit(
                                f"Review upstream path dependency {crate}: {name}"
                            )
    print(f"Fork metadata is current: {config['version']} from {config['upstream']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    prepare(parser.parse_args().check)
