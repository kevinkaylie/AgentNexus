## Summary / 概述

Brief description of what this PR does.

## Changes / 变更

- ...
- ...

## Test Plan / 测试计划

- [ ] New tests added (test IDs: )
- [ ] Existing tests updated
- [ ] `python main.py test` — all tests pass
- [ ] Manual testing against live relay (if applicable)

## Checklist

- [ ] Code follows project conventions (see CLAUDE.md)
- [ ] No secrets or private keys in committed files
- [ ] Write endpoints have `Depends(_require_token)` if applicable
- [ ] Async functions use `asyncio`, no blocking calls
- [ ] `common/` modules do not import from `node/` or `relay/`
