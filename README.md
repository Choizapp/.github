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

Pin the caller to `@v1` (or a more specific tag) to avoid surprises when the reusable workflow evolves. New backwards-compatible features go in `v1.x`; breaking changes require a new major (`@v2`).

## Related

- Linear issue: [CHOIZ-762](https://linear.app/choiz-app/issue/CHOIZ-762)
- First migrated repo: [Choizapp/checkout-core-mx](https://github.com/Choizapp/checkout-core-mx)
