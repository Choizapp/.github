# Choizapp `.github`

Org-level community health files and shared GitHub Actions workflows.

## Shared workflows

### `backend-coverage.yml` — JaCoCo coverage with patch-level gating

Reusable workflow for backend Java/Maven repos. Replaces the Codecov upload step in CircleCI with a self-hosted reporter that:

- Runs `mvn test` and parses `target/site/jacoco/jacoco.xml`
- Posts a single sticky comment on the PR with overall + per-file + patch coverage
- Enforces a **patch coverage** threshold on changed Java lines (default 90%)
- Shows the project's overall coverage with a configurable **target** (informational) and an optional **gating threshold** (hard fail)

**Why two-level gating:** repos with historical coverage below the 90% lineamiento can adopt the workflow without blocking every PR. Patch coverage stays strict (new code must be tested), overall is shown as informational and rises naturally over time.

### Minimal caller (repos without internal Maven deps)

`.github/workflows/coverage.yml` in the consumer repo:

```yaml
name: Coverage

on:
  pull_request:
    branches: [develop, master]

jobs:
  coverage:
    uses: Choizapp/.github/.github/workflows/backend-coverage.yml@v1
```

Defaults applied:
- `threshold-patch: 90` — patch coverage gate (hard)
- `threshold-overall: 0` — overall gate disabled (informational only)
- `target-overall: 90` — informational target shown in the comment

### Caller for repos using AWS CodeArtifact (internal Choiz deps)

```yaml
name: Coverage

on:
  pull_request:
    branches: [develop, master]

jobs:
  coverage:
    uses: Choizapp/.github/.github/workflows/backend-coverage.yml@v1
    with:
      use-codeartifact: true
```

### Overriding thresholds

```yaml
jobs:
  coverage:
    uses: Choizapp/.github/.github/workflows/backend-coverage.yml@v1
    with:
      threshold-patch: '85'
      threshold-overall: '85'
      target-overall: '90'
```

### Available inputs

| Input | Default | Description |
|---|---|---|
| `java-version` | `'17'` | JDK version for setup-java |
| `threshold-patch` | `'90'` | Gating threshold for patch coverage |
| `threshold-overall` | `'0'` | Gating threshold for overall coverage (0 = disabled) |
| `target-overall` | `'90'` | Informational target shown in the PR comment |
| `jacoco-xml` | `'target/site/jacoco/jacoco.xml'` | Path to the JaCoCo XML report |
| `use-codeartifact` | `false` | If `true`, authenticates via OIDC and pulls `CODEARTIFACT_TOKEN` |
| `aws-role-arn` | `arn:aws:iam::612700283677:role/github-actions-codeartifact` | IAM role for OIDC |
| `codeartifact-domain` | `'choizmaven'` | CodeArtifact domain |
| `codeartifact-domain-owner` | `'612700283677'` | CodeArtifact domain owner |
| `maven-settings-path` | `'.circleci/settings.xml'` | Path to Maven `settings.xml` inside the consumer repo |

### Prerequisites in the consumer repo

- `jacoco-maven-plugin` configured in `pom.xml` (`prepare-agent` + `report`)
- If `pom.xml` defines an explicit `<argLine>` inside `maven-surefire-plugin`, it must start with `@{argLine}` so JaCoCo's `prepare-agent` can inject its agent. Without this, the report is generated empty and the workflow has nothing to gate against.

## Versioning

Pin the caller to `@v1` (or a more specific tag like `@v1.3`) to avoid surprises when the reusable workflow evolves. New backwards-compatible features go in a fresh tag (`v1.4`, `v1.5`, ...); breaking changes require a new major (`@v2`).

`v*` tags are protected via a repository ruleset — they cannot be deleted, force-pushed, or rewritten. To ship a fix, create a new tag and have consumers update their `@v1.x` pin. The `@v1` pointer is therefore frozen at the current "stable" snapshot; bumping it requires temporarily lifting the ruleset.

## Security

This repo is **public** but contains only CI orchestration — no secrets, no proprietary code. Visibility implications:

- The AWS account ID and IAM role ARN are visible. Both are safe because the role's trust policy restricts assumption to `repo:Choizapp/*:pull_request`.
- The reusable workflow can be invoked from any repo in any org. Non-Choizapp callers will fail at the OIDC step (trust policy mismatch).
- Pushes to `main` require a PR; force-pushes and deletions are blocked. Tags matching `v*` are similarly protected.
- The shared script is checked out at the same commit SHA as the called workflow (`github.job_workflow_sha`), so script and workflow always travel together.

Report security issues privately to the repo owner before opening a PR.

### `sops-recipients.yml` — re-wrap a sops store when its recipients change

For repos that keep a committed, `sops` + `age` encrypted store (helios does). Adding a teammate means adding their public key to `.sops.yaml` **and** re-encrypting the data key for them with `sops updatekeys`, which only an existing recipient can run. This workflow does that second half with a **robot key**, so the human step disappears: the newcomer opens a PR with their public key, the bot commits the re-wrapped ciphertext to the same branch, and the merge is atomic.

On every run it first verifies each store still decrypts with the robot key — if `.sops.yaml` and the ciphertext have diverged, the check fails and says so.

Caller (`.github/workflows/store-recipients.yml` in the consumer repo):

```yaml
name: Store recipients

on:
  pull_request:
    paths: ['.secrets/.sops.yaml']
  push:
    branches: [main]
    paths: ['.secrets/.sops.yaml']

permissions:
  contents: write

jobs:
  rewrap:
    uses: Choizapp/.github/.github/workflows/sops-recipients.yml@v1
    secrets:
      robot-age-key: ${{ secrets.ROBOT_AGE_KEY }}
```

Inputs, all optional: `sops-config` (`.secrets/.sops.yaml`), `stores` (`.secrets/*/.secrets.enc`), `input-type` (`dotenv`), `sops-version`.

Setting it up once per repo: generate a keypair (`age-keygen`), add the **public** key to `.sops.yaml` as a recipient named for the robot, re-wrap once by hand, and put the **private** key in a repo secret. Keep its backup in an admin-only Vaultwarden note, like the data-pipelines robot. The trade-off to know: whoever can merge a PR that edits `.sops.yaml` can add a recipient, because the bot wraps for whatever the file says. Fine for read-only credentials; revisit before the store holds anything that writes.
