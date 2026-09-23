"""冻结规范包的加载与接收前校验（Profile §15.1/§15.9）。

**为什么必须真的做 schema 校验**：评审 B5 复现了 ``assignment.payload={}`` 被
202 ACK —— 原实现只确认 payload 是 dict，把"缺少 enforcement_requirements"当成
空列表，于是没有冻结输入/输出 schema/预算/期限的任务进入了 inbox。只断言几个字段
的测试无法发现这种问题，因此这里以**冻结 schema** 为唯一判据。

包位置：环境变量 ``CODE_REVIEW_PROFILE_PACKAGE``，否则使用本仓库内
``specs/profiles/code-review/v1``。包不可用时**失败关闭**（``unsupported_profile``）：
没有冻结 schema 就无法证明收到的是 Profile 消息，不允许降级为"少校验几个字段"。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from .errors import ProfileError

PACKAGE_ENV = "CODE_REVIEW_PROFILE_PACKAGE"

#: 本仓库内的默认位置（``agent_net/code_review/frozen.py`` → 仓库根）
_DEFAULT_RELATIVE = Path("specs") / "profiles" / "code-review" / "v1"

#: 已解析的 (包路径, registry, {schema 名: validator})，按路径缓存
_CACHE: Optional[tuple] = None


def package_root() -> Optional[Path]:
    """返回冻结规范包目录；不存在返回 ``None``。"""
    env = os.environ.get(PACKAGE_ENV)
    if env:
        candidate = Path(env)
    else:
        candidate = Path(__file__).resolve().parents[2] / _DEFAULT_RELATIVE
    return candidate if (candidate / "schemas").is_dir() else None


def reset_cache() -> None:
    """清空缓存（测试与换包后必须调用）。"""
    global _CACHE
    _CACHE = None


def _load() -> tuple:
    global _CACHE
    root = package_root()
    if root is None:
        raise ProfileError(
            "unsupported_profile",
            f"冻结规范包不可用（设置 {PACKAGE_ENV} 指向 specs/profiles/code-review/v1）；"
            "缺少冻结 schema 时不得接收 Profile 消息",
            scope="frozen_package",
        )
    if _CACHE is not None and _CACHE[0] == root:
        return _CACHE

    try:
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource
    except ImportError as exc:  # pragma: no cover - 依赖缺失属部署错误
        raise ProfileError(
            "unsupported_profile",
            f"缺少 jsonschema/referencing，无法执行冻结 schema 校验：{exc}",
            scope="frozen_package",
        ) from exc

    schemas: Dict[str, dict] = {}
    resources = []
    for path in sorted((root / "schemas").glob("*.schema.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        sid = doc.get("$id")
        if not sid:
            continue
        schemas[path.name] = doc
        resources.append((sid, Resource.from_contents(doc)))

    registry = Registry().with_resources(resources)
    validators = {
        name: Draft202012Validator(
            doc, registry=registry, format_checker=Draft202012Validator.FORMAT_CHECKER
        )
        for name, doc in schemas.items()
    }
    _CACHE = (root, registry, validators)
    return _CACHE


def available() -> bool:
    return package_root() is not None


def _problems(schema_name: str, document: Any, limit: int = 5) -> list[str]:
    _, _, validators = _load()
    validator = validators.get(schema_name)
    if validator is None:
        raise ProfileError(
            "unsupported_profile",
            f"冻结包缺少 schema {schema_name}",
            scope="frozen_package",
        )
    errors = sorted(validator.iter_errors(document), key=lambda e: list(e.path))
    return [f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors[:limit]]


def validate_document(schema_name: str, document: Any, *, code: str, scope: str) -> None:
    """校验任意文档；失败抛 ``ProfileError``（错误码可指定）。"""
    problems = _problems(schema_name, document)
    if problems:
        raise ProfileError(
            code,
            f"{schema_name} 校验失败：{problems[0]}",
            scope=scope,
            # 冻结 error.schema.json 是 additionalProperties:false：校验细节只能放
            # extensions，放顶层会让错误响应本身不合法（HTTP 契约矩阵抓到）。
            extra={"extensions": {"violations": problems}},
        )


def validate_envelope(envelope: Dict[str, Any]) -> None:
    """按冻结 ``envelope.schema.json`` 校验信封**及其按 type 的 payload**（B5）。

    该 schema 的 ``allOf`` 已经编码了每种 type 的必需信封字段与 payload schema，
    因此这一步同时覆盖：空 payload、缺 enforcement_requirements、未知字段、
    关联字段缺失（如 assignment 缺 run_id/attempt_id/assignment_epoch）。
    """
    validate_document("envelope.schema.json", envelope, code="invalid_output", scope="envelope")


def validate_artifact_ref(ref: Dict[str, Any]) -> None:
    """产物引用必须满足冻结 ``artifact_ref.schema.json``（B3）。

    评审复现：原响应多出 schema 禁止的 ``enforcement`` 字段，HCZJ 的严格校验会拒绝。
    """
    validate_document("artifact_ref.schema.json", ref, code="invalid_output", scope="artifact")
