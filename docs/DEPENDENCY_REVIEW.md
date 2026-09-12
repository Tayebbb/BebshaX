# Release Dependency Review

Reviewed 2026-09-09 for OPS-01/02/03/07/12. This review authorizes the scoped
dependency work below, not a production release, provider call, new model,
dataset download, major-version sweep, or commercial-use certification.

## Python Graph

The existing Python 3.12 environment is the compatibility baseline. Installed
versions become **constraints**, not a pip-freeze installation list. The uv
resolver computes the complete declared backend + ML + dev/build closure,
including platform markers, and obtains distribution hashes from PyPI. A
runtime-only subset is resolved against the same full lock. Every managed
install uses a hash-checked lock; local project wheels/editable installs use
`--no-deps --no-build-isolation` after the locked build requirements are present.
No package outside the declared dependency closure is installed merely because
it was present on the development machine.

| Component | Decision, Purpose, License, Activity, Necessity |
| --- | --- |
| uv 0.11.19 | Existing resolver, observed `uv --version` (2026-06-03 build). MIT/Apache-2.0, maintained by Astral. Universal Python 3.12 hash locking replaces the incomplete snapshot. Build-maintenance tool only; no host install or automatic update. |
| NumPy 2.5.2 / SciPy 1.18.1 / scikit-learn 1.9.0 | Preserve the exact installed reference-artifact runtime from `ml_persona/constraints.txt`. BSD-3-Clause, maintained scientific Python projects. Required for the existing CPU selector. No retraining, metadata rewriting, or numerical upgrades. |
| FastAPI / Starlette / uvicorn / Pydantic / SQLAlchemy / asyncpg | Preserve installed compatible versions through resolver constraints. MIT/BSD/Apache-2.0 family, maintained upstream projects. Existing HTTP/schema/persistence stack; no framework change. A clean audit is still required. |
| Freellmpool 0.11.4 | Preserve installed routing-library version, MIT, upstream maintained. The routing owner owns library-behavior changes and any later release evaluation. Do not silently adopt 0.13.0. |
| cramjam 2.12.0 | Reconcile the stale 2.11.0 snapshot with the installed compressor required by fastparquet. MIT, maintained upstream. Existing transitive dependency, not a new data engine. |
| pip-audit 2.10.1 | Existing declared audit tool, Apache-2.0, maintained by PyPA. Retain a reviewed exact version and its resolved closure. Advisory-service/network failure or vulnerabilities block CI; never use `--fix`. Dev/build only. |
| Pyright 1.1.412 | PyPI metadata verified this published version on 2026-09-09; the historical 1.1.413 pin does not exist and the resolver rejected it. MIT, maintained Microsoft/Pyright project and Python wrapper. Replaces CI's unpinned install. Necessary dev gate; establish a new measured baseline without suppressing errors. Its bundled JS entry is run with the pinned Node runtime, without automatic Node downloads. |
| PyYAML 6.0.3 | Existing uvicorn dependency, MIT, maintained upstream. Also declare explicitly for operations tests that parse YAML with `safe_load`. No new YAML engine. |
| nodeenv 1.10.0 / uvloop 0.22.1 | Resolver-required platform/tool edges: nodeenv (BSD-2-Clause) is Pyright wrapper's existing installer dependency, but operations bypasses its download path and uses provisioned Node. uvloop (MIT/Apache-2.0) is uvicorn's existing non-Windows standard-extra event loop. Both are maintained upstream packages, hash-pinned; Windows tests do not validate uvloop. |
| setuptools 84.0.0 / wheel 0.48.0 | Existing baseline build tools, MIT, maintained by PyPA. Include in the reviewed build closure so editable/project-wheel builds do not resolve separate unpinned isolation environments. |
| Other existing direct/transitive packages | Constrain existing installed versions first. Newly required transitive edges are resolver output, not permission to upgrade an existing dependency. Inventory and advisory evidence must accompany a release. |

Primary sources: [uv](https://github.com/astral-sh/uv),
[pip-audit](https://pypi.org/project/pip-audit/2.10.1/),
[Pyright wrapper](https://pypi.org/project/pyright/1.1.412/),
[Pyright](https://github.com/microsoft/pyright),
[PyYAML](https://pypi.org/project/PyYAML/6.0.3/),
[setuptools](https://pypi.org/project/setuptools/84.0.0/),
[wheel](https://pypi.org/project/wheel/0.48.0/).
Installed version metadata is compatibility evidence, not a security attestation.

## JavaScript And Images

The frontend owner controls root/frontend manifests and the root workspace lock.
Operations consumes that root graph from CI, Vercel and the web image, and must
report a missing or inconsistent root lock as a blocker. No nested-lock fallback.
Node 24 is the supported release family. The roadmap's Node 24.21.0 image tag
was absent from Docker Hub on inspection; the registry returned 24.20.0 tags.
Image versions and index digests must be verified against public registry
metadata, retained in `deploy/images.json`, and scanned before release.
Python stays in the 3.12 security-supported family; PostgreSQL stays 16 with
pgvector. nginx is a non-root static server/proxy, not a dev server.

Node (MIT and bundled notices), Python (PSF and bundled notices), nginx
(BSD-2-Clause), PostgreSQL (PostgreSQL License), and pgvector (PostgreSQL License)
remain necessary existing runtimes. Base OS packages carry separate licenses and
advisories. Digest pinning provides reproducibility, not freedom from CVEs.

## Data, Models And Commercial Release

CI action references were resolved from public GitHub refs to full commit IDs
on 2026-09-09: checkout v4, setup-python v5, setup-node v4, upload-artifact v4,
and gitleaks-action v2. These retain existing action families (MIT-licensed
GitHub actions and gitleaks), with least-privilege read access. Added
`aquasecurity/trivy-action` 0.35.0, Apache-2.0, actively maintained by Aqua:
necessary for image vulnerability and CycloneDX SBOM gates; build/CI only,
no local host installation and no image publication. Scanner downloads and
advisory database availability remain an executable CI gate. Node 24.20.0
bundles npm 11.19.0, verified from its upstream npm package metadata.

No pretrained weights or new datasets are approved here. Skip unknown rights.
Redistribution requires a reviewed inventory identifying source revision,
license, attribution, changes, approved use and exclusions for every bundle.
Synthetic status is not permission to redistribute. Existing non-commercial
profiles must not silently enter a commercial release. GSAP terms and competitive
product restrictions require the frontend owner's review and human acceptance;
package labels do not establish the product's license. Recovery manifests verify
integrity and lineage, not publisher authenticity or legal rights.

## Verification Status

Verified: universal 93-distribution full / 60-distribution runtime hash locks;
Windows hash-checked wheel download and a clean no-index install of both project
wheels; installed and clean-environment `pip-audit`, and installed `pip check`,
all exit 0. No shared-environment dependencies were changed. Numerical pins match
both locks. Local package skip notices are not project security certification.

Final foundation regressions: 25 Node tests and 28 Python tests passed, plus
4 existing FakeAdapter judge tests. Both quiet Compose profiles, bug-tier Ruff,
empty example parity, documentation links and scoped diff hygiene passed.

Pyright runs the published 1.1.412 CLI bin entrypoint, not the internal JS bundle
which lacks typeshed initialization. The final backend snapshot is 153 errors
and 2 warnings, kept blocking. Linux/image execution, CVE scans and frontend-owner
tooling upgrades remain outstanding. Current results are recorded in
[PRODUCTION_READINESS.md](PRODUCTION_READINESS.md). No live database, provider,
deployment, trained-artifact load or historical credential verification is implied.