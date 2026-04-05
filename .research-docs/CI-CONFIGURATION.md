# CI/CD Configuration

## ci.yml - Continuous Integration

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - run: pip install -e ".[dev]"
      - run: ruff check forecost/ tests/
      - run: ruff format --check forecost/ tests/

  test:
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.10", "3.11", "3.12"]
        os: [ubuntu-latest, macos-latest, windows-latest]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip
      - run: pip install -e ".[dev,forecast]"
      - run: pytest tests/ -v --tb=short -x

  smoke:
    runs-on: ubuntu-latest
    needs: [lint, test]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - run: pip install .
      - run: forecost --version
      - run: forecost --help
      - run: forecost demo
```

### Job Breakdown

**lint:**
- Python 3.12 only
- Installs dev dependencies (includes ruff)
- `ruff check`: Linting rules
- `ruff format --check`: Format validation

**test:**
- Matrix: 3 Python versions × 3 OS platforms = 9 jobs
- `fail-fast: false`: Run all combinations even if one fails
- Installs `[dev,forecast]` extras (statsmodels needed for tests)
- `pytest -v --tb=short -x`: Verbose, short tracebacks, fail fast

**smoke:**
- Depends on lint + test passing
- Installs from wheel (not editable)
- Basic CLI validation: version, help, demo

### Concurrency Control

```yaml
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
```

Cancels previous runs on new push (saves CI minutes).

---

## release.yml - PyPI Publication

```yaml
name: Release to PyPI
on:
  release:
    types: [published]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install build
      - run: python -m build
      - uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/

  test-install:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist/
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install dist/*.whl
      - run: forecost --version
      - run: forecost demo

  publish:
    needs: [build, test-install]
    runs-on: ubuntu-latest
    environment:
      name: pypi
      url: https://pypi.org/p/forecost
    permissions:
      id-token: write
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist/
      - uses: pypa/gh-action-pypi-publish@release/v1
```

### Release Flow

1. **build**: Creates wheel + sdist, uploads as artifact
2. **test-install**: Downloads artifact, installs wheel, runs smoke tests
3. **publish**: Uses PyPA's trusted publishing (OIDC, no API key needed)

### Security

- **Trusted publishing**: GitHub → PyPI OIDC flow, no secrets in repo
- **Environment protection**: PyPI deployment requires manual approval (if configured)
- **Test before publish**: Install-tested wheel before publication

### Trigger

Only runs on GitHub Releases (not tags):
```yaml
on:
  release:
    types: [published]
```

---

## CI/CD Best Practices Demonstrated

| Practice | Implementation |
|----------|----------------|
| Matrix testing | 3 Python × 3 OS combinations |
| Fail fast disabled | `fail-fast: false` for full matrix results |
| Editable vs wheel testing | Dev uses `-e`, smoke uses wheel |
| Artifact passing | build → test-install → publish |
| Lint before test | Separate job, faster feedback |
| Smoke tests | Verify actual install works |
| Trusted publishing | OIDC, no API tokens in secrets |
