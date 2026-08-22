# Git hooks

```bash
git config core.hooksPath .githooks
```

One command, run once per clone. `CONTRIBUTING.md` lists it in the setup block and
`sdip doctor` reports whether it is active.

## Why a hook when three other layers already exist

| Layer | Catches a leak | When |
|---|---|---|
| **`.githooks/pre-commit`** | **before it exists** | at `git commit` |
| `.gitignore` | an accidental `git add -A` | at `git add` |
| `sdip doctor` → `publication-firewall` | index and `HEAD` | on demand |
| CI `firewall` job | any commit, any ref | on every PR and push |

Only the hook prevents the leak. Every other layer *reports* one that has already
happened, and once a path is in a commit the remedy is a history rewrite — cheap while
the repository has two commits and one contributor, expensive the moment anyone has
cloned it.

`git commit --no-verify` skips the hook. It does not skip `sdip doctor` or the CI job.
That asymmetry is deliberate: a contributor in a hurry can get past the convenience
layer and still cannot get a leak merged.
