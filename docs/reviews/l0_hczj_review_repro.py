"""Review probe of HCZJ attribution with its existing isolated service fixture."""
import os
import runpy
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HCZJ = ROOT.parent / "Hczj_Assistant_Agent"
sys.path.insert(0, str(HCZJ))
os.environ["CODE_REVIEW_PROFILE_PACKAGE"] = str(ROOT / "specs/profiles/code-review/v1")
helpers = runpy.run_path(str(HCZJ / "tests/unit/test_code_review_service.py"))
original = helpers["delivered"].__globals__["fixture"]
def substituted(name):
    result = original(name)
    if name.startswith("09_"):
        result["reviewer_id"] = "unassigned:reviewer"
    return result
helpers["delivered"].__globals__["fixture"] = substituted
with tempfile.TemporaryDirectory() as directory:
    setup = helpers["setup"].__wrapped__(Path(directory))
    context = next(setup)
    try:
        ack, assignment, worker, envelope, view, report = helpers["delivered"](context)
        print("REVIEWER_BINDING", worker["principal_id"], report["reviewer_id"], view["state"], view["receipts"][0]["payload"]["kind"])
    finally:
        context[0].store.close()
        setup.close()
