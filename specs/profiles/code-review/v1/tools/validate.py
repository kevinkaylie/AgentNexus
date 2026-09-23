#!/usr/bin/env python3
"""Code Review Collaboration Profile v1 -- package self-check.

Usage (from anywhere):
    python specs/profiles/code-review/v1/tools/validate.py

Checks:
1. every schemas/*.schema.json parses and has a unique $id;
2. valid fixtures pass their bound schema;
3. invalid fixtures FAIL their bound schema (otherwise the schema missed a MUST);
4. no orphan fixtures outside fixtures/index.json;
5. digest vectors match the actual bytes of the artifact_body fixture (Profile 15.3 / CP-23);
6. cp-matrix references exist;
7. the binding contract's error table covers exactly the error.schema.json enum;
8. the T1-T6 closure tracker is self-consistent (no false closure, no premature enablement);
9. if manifest.json exists, its registered digests match the files on disk.

Non-zero exit means failure. This script only covers structure and digests; behavioural
semantics (state, lease, CAS, publication-unknown) must be covered by behaviour tests.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
except ImportError as exc:  # pragma: no cover
    print(f"[FATAL] jsonschema>=4.18 with referencing is required: {exc}")
    sys.exit(2)

BASE = Path(__file__).resolve().parent.parent
SCHEMAS = BASE / "schemas"
FIXTURES = BASE / "fixtures"


def load_json(path: Path):
    raw = path.read_bytes()
    text = raw.decode("utf-8")  # strict UTF-8, no character substitution
    return json.loads(text), raw


def build_registry():
    resources = []
    ids = {}
    for path in sorted(SCHEMAS.glob("*.schema.json")):
        schema, _ = load_json(path)
        sid = schema.get("$id")
        if not sid:
            raise SystemExit(f"[FAIL] {path.name} has no $id")
        if sid in ids:
            raise SystemExit(f"[FAIL] duplicate $id {sid} in {path.name} and {ids[sid]}")
        ids[sid] = path.name
        resources.append((sid, Resource.from_contents(schema)))
    return Registry().with_resources(resources), ids


def validator_for(schema_name: str, registry: Registry):
    schema, _ = load_json(SCHEMAS / schema_name)
    return Draft202012Validator(schema, registry=registry, format_checker=Draft202012Validator.FORMAT_CHECKER)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_digest_vectors(failures: list[str]) -> int:
    vectors_path = FIXTURES / "digest_vectors.json"
    if not vectors_path.exists():
        failures.append("missing fixtures/digest_vectors.json")
        return 0
    spec, _ = load_json(vectors_path)
    canonical = FIXTURES / spec["canonical_artifact_body"]
    if not canonical.exists():
        failures.append(f"digest_vectors points to a missing artifact_body: {spec['canonical_artifact_body']}")
        return 0

    base_bytes = canonical.read_bytes()
    transforms = {
        "append_newline": lambda b: b + b"\n",
        "compact_reserialize": lambda b: json.dumps(
            json.loads(b.decode("utf-8")), ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8"),
        "indent2_reserialize": lambda b: json.dumps(
            json.loads(b.decode("utf-8")), ensure_ascii=False, indent=2
        ).encode("utf-8"),
    }

    checked = 0
    for vector in spec["vectors"]:
        expected = vector.get("expected")
        if expected is None:
            continue  # expected_same_as vectors are behaviour-test territory
        data = base_bytes
        transform_id = vector.get("transform_id")
        if transform_id:
            if transform_id not in transforms:
                failures.append(f"{vector['id']}: unknown transform_id {transform_id}")
                continue
            data = transforms[transform_id](base_bytes)
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        if digest != expected["digest"] or len(data) != expected["byte_length"]:
            failures.append(
                f"{vector['id']} digest mismatch: got {digest}/{len(data)}, "
                f"expected {expected['digest']}/{expected['byte_length']}"
            )
        checked += 1
    return checked


def resolve_ref(ref: str) -> Path:
    ref = ref.split("#", 1)[0]  # 允许 cp-matrix 用 #anchor 指向行为规范中的具体用例
    if ref.startswith(("schemas/", "fixtures/", "bindings/")):
        return BASE / ref
    return FIXTURES / ref


def check_cp_matrix(failures: list[str]) -> int:
    spec, _ = load_json(FIXTURES / "cp-matrix.json")
    count = 0
    for case in spec["cases"]:
        for ref in case.get("fixtures", []):
            if not resolve_ref(ref).exists():
                failures.append(f"{case['id']} references a missing file: {ref}")
        count += 1
    return count


def check_contract_error_table(failures: list[str]) -> int:
    """契约 §7 的错误映射表必须与本包 error.schema.json 枚举一致（评审 R2-1/R2-2）。

    机械保证：契约里出现未登记的 code → 失败；枚举里的码未出现在表中 → 失败。
    于是"§10.1 引入 413 却没有对应表行"这类遗漏会直接让自检变红。
    """
    import re

    contract = BASE / "bindings" / "l0-service-contract.md"
    if not contract.exists():
        return 0
    text = contract.read_text(encoding="utf-8")
    enum = set(load_json(SCHEMAS / "error.schema.json")[0]["properties"]["code"]["enum"])

    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("| HTTP | code |")), None)
    if start is None:
        failures.append("contract section 7 error table not found (header '| HTTP | code |')")
        return 0

    used: set = set()
    unknown: list = []
    for line in lines[start + 2:]:
        if not line.startswith("|"):
            break
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        for token in re.split(r"[/\s]+", cells[1]):
            token = token.strip()
            if re.fullmatch(r"[a-z][a-z0-9_]+", token or ""):
                if token in enum:
                    used.add(token)
                else:
                    unknown.append(token)

    if unknown:
        failures.append(f"contract section 7 references unregistered codes: {sorted(set(unknown))}")
    missing = sorted(enum - used)
    if missing:
        failures.append(f"contract section 7 does not cover enum codes: {missing}")
    if "scope=read_limit" not in text:
        failures.append("contract does not annotate scope=read_limit for the 413 cause (R2-2)")
    return len(used)


def check_evidence_tracker(failures: list[str]) -> int:
    """T1–T6 关闭证据校验（bindings/evidence/closure-checklist.json）。

    开放是合法状态：本步失败只代表「虚假关闭」「声明与实际不一致」或「提前放行」。
    校验逻辑集中在 tools/check_evidence.py，避免两处各写一套口径。
    """
    import importlib.util

    checker_path = Path(__file__).resolve().parent / "check_evidence.py"
    if not checker_path.exists():
        failures.append("missing tools/check_evidence.py (T1-T6 closure checker)")
        return -1
    spec = importlib.util.spec_from_file_location("code_review_check_evidence", checker_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    print("--- T1–T6 收口清单（tools/check_evidence.py）---")
    code = module.main()
    if code == 2:
        failures.append("T1-T6 closure checklist/templates are broken (check_evidence exit 2)")
    elif code == 1:
        failures.append("T1-T6 closure checklist failed: false closure, declaration mismatch, or premature enablement")
    return code


def check_manifest(failures: list[str]) -> int:
    manifest_path = BASE / "manifest.json"
    if not manifest_path.exists():
        print("[SKIP] manifest.json not generated yet (run tools/make_manifest.py)")
        return 0
    manifest, _ = load_json(manifest_path)
    checked = 0
    for entry in manifest.get("files", []):
        p = BASE / entry["path"]
        if not p.exists():
            failures.append(f"manifest registers a missing file: {entry['path']}")
            continue
        actual = sha256_file(p)
        if actual != entry["sha256"]:
            failures.append(f"manifest digest mismatch: {entry['path']} actual {actual}")
        elif p.stat().st_size != entry["byte_length"]:
            failures.append(f"manifest byte_length mismatch: {entry['path']}")
        else:
            checked += 1
    return checked


def main() -> int:
    failures: list[str] = []
    registry, ids = build_registry()
    print(f"[OK] schemas: {len(ids)} files, unique $id")

    index, _ = load_json(FIXTURES / "index.json")

    valid_bad = 0
    for item in index["valid"]:
        path = FIXTURES / item["file"]
        if not path.exists():
            failures.append(f"missing valid fixture: {item['file']}")
            continue
        doc, _ = load_json(path)
        v = validator_for(item["schema"], registry)
        errors = sorted(v.iter_errors(doc), key=lambda e: list(e.path))
        if errors:
            valid_bad += 1
            failures.append(f"valid fixture rejected by {item['schema']}: {item['file']} -> {errors[0].message[:220]}")
    print(f"[{'OK' if valid_bad == 0 else 'FAIL'}] valid fixtures accepted: {len(index['valid']) - valid_bad}/{len(index['valid'])}")

    invalid_ok = 0
    for item in index["invalid"]:
        path = FIXTURES / item["file"]
        if not path.exists():
            failures.append(f"missing invalid fixture: {item['file']}")
            continue
        doc, _ = load_json(path)
        v = validator_for(item["schema"], registry)
        errors = list(v.iter_errors(doc))
        if errors:
            invalid_ok += 1
            print(f"      - {item['file']} rejected as expected: {errors[0].message[:110]}")
        else:
            failures.append(f"invalid fixture PASSED validation (schema missed a MUST): {item['file']} -- {item['rule']}")
    print(f"[{'OK' if invalid_ok == len(index['invalid']) else 'FAIL'}] invalid fixtures rejected: {invalid_ok}/{len(index['invalid'])}")

    listed = {item["file"] for item in index["valid"]} | {item["file"] for item in index["invalid"]}
    orphans = [f"{sub}/{p.name}" for sub in ("valid", "invalid") for p in sorted((FIXTURES / sub).glob("*.json")) if f"{sub}/{p.name}" not in listed]
    for rel in orphans:
        failures.append(f"orphan fixture not listed in index.json: {rel}")
    print(f"[{'OK' if not orphans else 'FAIL'}] orphan fixtures: {len(orphans)}")

    checked = check_digest_vectors(failures)
    print(f"[{'OK' if checked else 'SKIP'}] digest vectors verified: {checked}")

    cp_count = check_cp_matrix(failures)
    print(f"[OK] cp-matrix cases: {cp_count}")

    contract_codes = check_contract_error_table(failures)
    print(f"[{'OK' if contract_codes else 'SKIP'}] contract error table codes: {contract_codes}")

    evidence_code = check_evidence_tracker(failures)
    print(f"[{'OK' if evidence_code == 0 else 'FAIL' if evidence_code > 0 else 'SKIP'}] T1-T6 closure tracker (exit {evidence_code})")

    m_checked = check_manifest(failures)
    if m_checked:
        print(f"[OK] manifest files verified: {m_checked}")

    if failures:
        print("\n[FAILURES]")
        for f in failures:
            print(" -", f)
        return 1

    print("\n[PASS] package self-check passed (structure + digests). Behavioural semantics still require CP behaviour tests.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
