# Wholesym fork maintenance

This repository publishes five symbol libraries from `mstange/samply`.
The Rust source, library names, and APIs remain unchanged.
The registry names use the `-stackpulse` suffix.
The repository retains the upstream history and fixtures.

All five packages use one version in `fork/config.toml`:

- `samply-debugid-stackpulse`
- `samply-object-stackpulse`
- `samply-symbols-stackpulse`
- `samply-api-stackpulse`
- `wholesym-stackpulse`

The original MIT and Apache-2.0 licenses apply.
Each published package contains both license files and the original copyright notices.
The manifests identify the metadata changes.

## Use the fork

```toml
[dependencies]
wholesym = { package = "wholesym-stackpulse", version = "0.1.0", features = ["api"] }
```

This alias keeps Rust imports such as `use wholesym::SymbolManager` unchanged.
The fork version is separate from the upstream crate versions.

## Update from upstream

Start from a clean checkout with Python 3.11 or later and current stable Rust.
Run this command with the upstream revision and the next fork version:

```sh
python3 fork/update.py <upstream-revision> <new-fork-version>
```

The command creates a branch, merges upstream, and regenerates the package metadata.
It resolves conflicts in generated manifests and keeps the fork workflow.
It stops on source conflicts or new path dependencies that need another fork.
It stages the result for review. It does not commit, push, or publish.

Run these checks before the commit:

```sh
python3 fork/prepare.py --check
cargo test --workspace --all-features --locked
cargo publish --workspace --dry-run --locked --allow-dirty
git diff --cached
```

Commit and push the update branch. Merge it after the Linux and macOS checks pass.

## Publish

Use the clean release commit on `main`:

```sh
cargo publish --workspace --locked
```

Cargo publishes the five packages in dependency order.
Authenticate with `cargo login` before the first publication.
No fork-specific release service or permanent GitHub secret is necessary.

Do not edit the generated manifests or README prefixes by hand.
To change fork metadata, edit `fork/config.toml` or `fork/prepare.py`.
Then run `python3 fork/prepare.py`.
