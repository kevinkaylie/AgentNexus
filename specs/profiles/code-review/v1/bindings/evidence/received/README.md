# received/ — 回填后的证据记录落点

把 `../templates/T{n}.json` 复制到这里，命名 `T{n}.json`，逐字段回填。

- 只放 **`T1.json` … `T6.json`** 六个文件；不要改文件名，否则无法与 `closure-checklist.json` 对应。
- 每条 record 的 `status` 改为 `closed` 前，必须清除该 record 内**所有** `__TODO__` 占位符。
- `__TODO__` 开头的 `item_status_reason` 也必须替换为实际说明。
- 原始字节用 base64 承载，`sha256` 与 `byte_length` 会被重算，填错即校验失败。
- 不要写入任何凭据明文（Bearer 值、GitLab PRIVATE-TOKEN、Admin Cookie）。

校验：

```bash
python ../../tools/check_evidence.py
```

未凑齐证据时保持 `item_status: "open"` 是合法且被鼓励的——校验脚本只拒绝**声称关闭但没有证据**。
