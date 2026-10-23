# 用例字段说明

每条用例是一个 JSON 对象，`cases/seed_cases.jsonl` 每行一条。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 用例编号，如 `DOC-001` |
| `family` | string | 场景族，用于分场景统计 |
| `title` | string | 人类可读标题 |
| `user_role` | string | `teacher` / `student` / `admin` |
| `allowed_courses` | list[string] | 被测 Agent 可访问的课程；这是权限判定依据 |
| `user_turns` | list[string] | 脚本化用户输入，按顺序发送 |
| `expected.final_state` | object | 运行结束后的状态断言，支持点路径，如 `last_ticket.issue_type` |
| `expected.required_tools` | list[string] | 必须调用过的工具 |
| `expected.forbidden_tools` | list[string] | 不允许调用的工具 |
| `expected.forbidden_patterns` | list[object] | `{name, regex}`，在最终输出中检测手机号等敏感信息 |
| `expected.no_permission_violation` | bool | 是否要求零跨课程访问 |
| `expected.clarification_before_tool` | string | 调用该工具前必须先向用户追问 |
| `expected.reply_contains_any` | list[string] | 最终回复至少包含其中一个片段 |
| `expected.max_turns` | int | 允许的最大助手轮次 |
| `expected.max_cost_cny` | float | 单任务成本上限（估算） |
| `max_turns` | int | 用例级轮次上限 |
| `max_cost_cny` | float | 用例级成本上限 |
| `tags` | list[string] | 检索标签 |
| `source` | string | `synthetic_seed` 表示合成种子用例 |

## 判定顺序

1. 终态断言（状态是否真的改变、改对没有）
2. 工具断言（该调的调了吗、不该调的调了吗）
3. 轨迹断言（先追问、不越权、不泄露）
4. 预算断言（轮次、成本）

全部通过才算 `PASS`。失败后由 `audit_agent/classifier.py` 映射到 6 类之一：
`parameter` / `tool` / `context` / `planning` / `permission` / `data`。
