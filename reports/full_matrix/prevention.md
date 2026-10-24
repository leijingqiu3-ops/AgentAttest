# 在线拦截回放（counterfactual）

数据：reports/full_matrix，共 280 条 trace。失败 93 条，可拦 44 条（执行前 39 + 出口脱敏 5），误伤 0 条。

| 故障模式 | 运行 | 失败 | 执行前拦下 | 出口脱敏 | 仍漏 |
|---|---:|---:|---:|---:|---:|
| `context_drop` | 40 | 11 | 0 | 0 | 11 |
| `early_stop` | 40 | 36 | 0 | 0 | 36 |
| `none` | 40 | 0 | 0 | 0 | 0 |
| `pii_leak` | 40 | 5 | 0 | 5 | 0 |
| `policy_ignore` | 40 | 11 | 10 | 0 | 1 |
| `skip_clarify` | 40 | 5 | 4 | 0 | 1 |
| `wrong_arg` | 40 | 25 | 25 | 0 | 0 |

命中规则：{"task_contract:course_id": 20, "task_contract:ticket_id": 5, "course_scope": 5, "refund_window": 5, "task_contract:student_id": 4}

> A block means the tool call never executed. The agent's behaviour after a denial is unknown, so this is an upper bound on prevention, not a success rate. Outbound hits are post-hoc: they only become preventive if replies are routed through send_reply, which the synthetic target does not always do.
