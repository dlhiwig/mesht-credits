# MESHT / CREDITS — Program Control

A dependency-free, responsive, eight-tab engineering and leadership dashboard.

## Run locally

From repository root:

```sh
python3 -m http.server 8000
```

Open http://localhost:8000/dashboard/ . Do not open index.html via file://; browsers restrict local JSON fetches. No build tool, CDN, API key, or login required.

## Views

Overview, Phases & gates, Engineering, Quality & evidence, Risk register, Decisions, Reports, Release readiness. Gates and risks have CSV export; browser Print can save a PDF.

## Provenance and limitations

The reviewed `dashboard/data/project.json` register controls completion metrics. **Only gates explicitly marked passed with acceptance evidence count as complete.** Partial and blocked gates do not. Phase Two through Phase Five criteria are proposals, not delivery commitments.

The browser optionally fetches public GitHub data for branch SHA, pull requests and workflow runs. API failures/rate limits are shown, not concealed. GitHub CI success does not automatically satisfy any gate. Python test outcomes in the source reports are locally reported; Rust CI was observed passing. No power-loss, independent checkpoint, or concurrency assurance is claimed.

Risk scores are subjective 1–5 likelihood × impact assessments; owner fields represent roles, not individual assignments. Do not commit member records, private keys or secrets into the public register.

Update gate evidence and risk posture through reviewed pull requests, ideally weekly. Source documents are PHASE-ZERO.md, PHASE-1-PLAN.md and PHASE-1-REPORT.md.

## Validation

```sh
python3 dashboard/scripts/validate.py
```

Dashboard CI validates metadata consistency; it is not a ledger test suite or security assessment.

## Deployment

The dashboard can be published with GitHub Pages or any static host. This PR does not alter Pages settings or create a public deployment.
