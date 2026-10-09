"""Validate dashboard data and references, without dependencies."""
import json
from pathlib import Path
root = Path(__file__).resolve().parents[2]
data = json.loads((root / "dashboard/data/project.json").read_text())
assert data["version"] == 1
phases = {p["id"] for p in data["phases"]}
gates = data["gates"]
assert len({g["id"] for g in gates}) == len(gates)
assert len({r["id"] for r in data["risks"]}) == len(data["risks"])
for g in gates:
    assert g["phase"] in phases
    assert g["status"] in ("passed", "partial", "blocked", "not_started")
    assert all(g[k] for k in ("name", "owner", "acceptance"))
    if g["evidence"]:
        assert (root / g["evidence"]).exists(), g["evidence"]
for r in data["risks"]:
    assert 1 <= r["likelihood"] <= 5 and 1 <= r["impact"] <= 5
for report in data["reports"]:
    assert (root / report["path"]).exists(), report["path"]
html = (root / "dashboard/index.html").read_text()
for tab in ("overview", "phases", "engineering", "quality", "risks", "decisions", "reports", "release"):
    assert f'id="{tab}"' in html
    assert f'data-tab="{tab}"' in html
assert "./data/project.json" in html
print(f"VALID: {len(data['phases'])} phases, {len(gates)} gates, {len(data['risks'])} risks")
