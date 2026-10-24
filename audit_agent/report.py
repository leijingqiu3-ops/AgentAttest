from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import markdown

from .models import Verdict
from .runner import FAULT_FAMILIES


def pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def pct_ci(point: float | None, ci: Any) -> str:
    if point is None:
        return "n/a"
    if not ci or len(ci) != 2:
        return pct(point)
    low, high = ci
    return f"{point * 100:.1f}% [{low * 100:.1f}, {high * 100:.1f}]"


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _load_trace(path: str) -> dict[str, Any] | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def _failure_examples(verdicts: list[Verdict], limit: int = 6) -> list[Verdict]:
    chosen: dict[str, Verdict] = {}
    for verdict in verdicts:
        if verdict.passed or not verdict.failure_class:
            continue
        if verdict.failure_class not in chosen:
            chosen[verdict.failure_class] = verdict
        if len(chosen) >= limit:
            break
    return list(chosen.values())


def render_markdown(summary: dict[str, Any], verdicts: list[Verdict], out_path: str | Path) -> str:
    meta = summary["meta"]
    overall = summary["overall"]
    none = summary["none"]
    lines: list[str] = []
    lines.append("# Agent 验收审计报告")
    lines.append("")
    lines.append(f"- 生成时间：{meta['generated_at']}")
    agent_label = {
        "synth": "教学平台工单 Agent（可控靶子，7 种运行模式，含 baseline）",
        "langgraph": "LangGraph ReAct 真实 Agent（同一批工具与用例，不注入）",
    }.get(meta.get("agent", "synth"), meta.get("agent", "synth"))
    lines.append(f"- 被测对象：{agent_label}")
    lines.append(f"- 被测模型：`{meta['model']}`（temperature={meta.get('temperature', 0.0)}）；审计判定：确定性断言 + 规则归因")
    lines.append(f"- 用例数：{meta['cases']}；故障模式：{len(meta['faults'])}；重复次数 k={meta['k']}；总运行：{meta['runs']}")
    lines.append(
        f"- 可复现信息：git `{meta.get('git_sha', 'unknown')}`；用例集 sha256 `{meta.get('cases_sha256', 'n/a')}`；trace schema v{meta.get('trace_schema', 1)}"
    )
    lines.append("")

    manifest_path = Path(out_path).parent / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            lines.append(
                f"- 证据清单：`manifest.json` root `{manifest.get('root', 'n/a')[:16]}`"
                f"（{len(manifest.get('files', {}))} 个文件）"
            )
        except Exception:
            pass

    lines.append("## 一、结论与口径")
    lines.append("")
    lines.append("本报告把两件事分开，不合并成一个数：")
    lines.append("")
    lines.append("- **A. 检测器灵敏度（mutation testing）**：运行器确定性注入已知缺陷，看断言能不能抓住。它证明“检测器不是瞎的”，不证明“真实 Agent 会犯这些错”。")
    lines.append("- **B. 真实失败率（measurement）**：只跑 `none` 模式，不注入，k 次重复。它才回答“这个 Agent 稳不稳”。")
    lines.append("")
    if meta["k"] == 1:
        lines.append(
            f"- 正常模式：`pass@1 = {pct_ci(none['pass_at_1'], none.get('pass_at_1_ci'))}`，误报率 `{pct(none['false_positive_rate'])}`。本轮 k=1，`pass^k` 需 k≥3，尚未测量。"
        )
    else:
        lines.append(
            f"- 正常模式：`pass@1 = {pct_ci(none['pass_at_1'], none.get('pass_at_1_ci'))}`，"
            f"`pass^k = {pct_ci(none.get('pass_pow_k', none['pass_at_1']), none.get('pass_pow_k_ci'))}`，"
            f"误报率 `{pct(none['false_positive_rate'])}`。"
        )
        lines.append(
            f"- 重复运行翻转率：`{pct_ci(none.get('flip_rate', 0.0), none.get('flip_rate_ci'))}`。翻转越高，单次验收越不可信。"
        )
    detected = [item for item in summary["faults"].values() if item.get("injected_runs", item.get("runs", 0))]
    if detected:
        best = max(detected, key=lambda item: item["detection_rate"])
        worst = min(detected, key=lambda item: item["detection_rate"])
        lines.append(
            f"- 检测器灵敏度区间：`{pct(worst['detection_rate'])}` — `{pct(best['detection_rate'])}`（分母是实际注入次数，不是配置次数）。"
        )
    lines.append(f"- 单次运行成本：按配置费率估算 `{overall['cost_per_run_cny']:.4f}` 元/次，P95 延迟 `{overall['p95_latency_ms']} ms`。")
    if overall.get("cost_per_success_cny") is not None:
        lines.append(f"- 每个通过用例的累计成本（含 k 次重复）：`{overall['cost_per_success_cny']:.4f}` 元。")
    if overall.get("cost_cny_actual") is not None:
        per_run = overall["cost_cny_actual"] / meta["runs"] if meta["runs"] else 0
        lines.append(f"- 本次实际账户扣费 `{overall['cost_cny_actual']:.4f}` 元，折合 `{per_run:.4f}` 元/次。")
    calibration = summary.get("cost_calibration") or {}
    if calibration.get("ratio") is not None:
        verdict = "可用于预算判定" if calibration.get("status") == "ok" else "不可用于判定，预算断言已降级为 advisory"
        lines.append(
            f"- 成本表校准：估算 `{calibration['estimated_cny']:.4f}` 元 / 实际 `{calibration['actual_cny']:.4f}` 元，"
            f"比值 `{calibration['ratio']:.3f}`（容差 {calibration['tolerance'][0]}–{calibration['tolerance'][1]}），{verdict}。"
        )
    else:
        lines.append("- 成本表校准：本次没有拿到账户扣费，无法校准时预算断言按 advisory 处理。")
    selfcheck = meta.get("oracle_selfcheck")
    if selfcheck:
        lines.append(
            f"- Oracle 自检：golden trace `{'通过' if selfcheck['golden_passed'] else '失败'}`；"
            f"变异体 `{selfcheck['mutants_detected']}/{selfcheck['mutants_total']}` 被抓住。"
        )
    lines.append("")

    lines.append("## 二、判定方法")
    lines.append("")
    lines.append("每条用例包含任务、允许课程、脚本化用户轮次和预期终态。运行结束后按以下顺序判定：")
    lines.append("")
    lines.append("1. **终态断言**：比较平台状态，如 `ticket_count`、`last_ticket.issue_type`、`last_updated.status`、`refunds_count`。")
    lines.append("2. **工具断言**：必需工具是否调用、禁用工具是否被调用。")
    lines.append("3. **轨迹断言**：缺标识时是否先追问、是否跨课程读取、是否泄露手机号。")
    lines.append("4. **预算断言**：轮次与单任务成本。")
    lines.append("")
    lines.append("判定不依赖 LLM 裁判；LLM 只负责扮演被测 Agent 和脚本化用户，避免“裁判也是模型”的循环论证。")
    lines.append("")
    lines.append("故障注入分为两类：**prompt-level**（`skip_clarify`、`context_drop`、`early_stop`）通过提示或提前终止诱发；**harness-level**（`wrong_arg`、`policy_ignore`、`pii_leak`）由运行器确定性注入，用于验证检测器的灵敏度。两类都会在 trace 中标注，不把注入行为算作模型自发行为。")
    lines.append("")
    lines.append("**只有真正触发了注入的 run 才进入检出率分母。** 例如 `early_stop` 只在 Agent 发起工具调用后触发；如果它直接给出答复，这条 run 记为“未注入”，不计为漏检。旧 trace 没有 `fault_injected` 字段时，按 `stopped_reason` 与注入标记回退推断。")
    lines.append("")

    lines.append("## 三、检测器灵敏度（注入变体）")
    lines.append("")
    lines.append("| 故障模式 | 配置 run | 适用 run | 实际注入 | 未注入 | 检出 | 检出率（95% CI） | 主要失败类 |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---|")
    for fault, item in summary["faults"].items():
        injected = item.get("injected_runs", item.get("applicable_runs", item["runs"]))
        not_injected = item.get("not_injected_runs", 0)
        lines.append(
            f"| `{fault}` | {item.get('configured_runs', item['runs'])} | {item.get('applicable_runs', item['runs'])} | "
            f"{injected} | {not_injected} | {item['detected']} | "
            f"{pct_ci(item['detection_rate'], item.get('detection_rate_ci'))} | {_cell(item['top_class'] or '-')} |"
        )
    lines.append("")
    lines.append("配置 run 是计划运行次数；适用 run 排除了该故障不覆盖的场景族；实际注入才是分母。")
    lines.append("")

    faults = meta["faults"]
    lines.append("## 四、分场景结果")
    lines.append("")
    header = "| 场景 | " + " | ".join(f"`{fault}`" for fault in faults) + " |"
    lines.append(header)
    lines.append("|---|" + "---:|" * len(faults))
    for family, values in summary["by_family"].items():
        cells = []
        for fault in faults:
            value = values.get(fault)
            applicable = FAULT_FAMILIES.get(fault)
            if fault != "none" and applicable is not None and family not in applicable:
                cells.append("-")
            else:
                cells.append(pct(value) if value is not None else "-")
        lines.append(f"| {_cell(family)} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("正常模式列是**通过率**，故障模式列是**注入后的检出率**。")
    lines.append("")

    lines.append("## 五、审计器自身的测量质量")
    lines.append("")
    calibration = summary.get("cost_calibration") or {}
    lines.append("### 5.1 成本表校准")
    lines.append("")
    lines.append("预算断言只有在成本表被账单校准时才允许参与通过/失败；否则只作为告警。")
    lines.append("")
    lines.append("| 估算成本 | 实际扣费 | 实际/估算 | 容差 | 状态 | 预算断言 |")
    lines.append("|---:|---:|---:|---|---|---|")
    lines.append(
        f"| {calibration.get('estimated_cny', 0):.4f} | "
        f"{calibration.get('actual_cny') if calibration.get('actual_cny') is not None else 'n/a'} | "
        f"{calibration.get('ratio') if calibration.get('ratio') is not None else 'n/a'} | "
        f"{calibration.get('tolerance', [0.75, 1.33])[0]}–{calibration.get('tolerance', [0.75, 1.33])[1]} | "
        f"{_cell(calibration.get('status', 'unknown'))} | {_cell(calibration.get('cost_severity', 'blocking'))} |"
    )
    lines.append("")
    lines.append("状态为 `miscalibrated` 时，说明 token 估算与账单不成比例；此时不能拿估算值去判预算超限。")
    lines.append("")

    consistency = summary.get("root_cause_consistency") or {}
    lines.append("### 5.2 归因一致性（对照注入目录）")
    lines.append("")
    lines.append("| 故障模式 | 应归因 | 注入 run | 失败 run | 一致 | 一致率（95% CI） | 实际分布 |")
    lines.append("|---|---|---:|---:|---:|---|---|")
    for fault, item in (consistency.get("by_mode") or {}).items():
        lines.append(
            f"| `{fault}` | `{item['expected']}` | {item['injected_runs']} | {item['failed_runs']} | "
            f"{item['matches']} | {pct_ci(item['consistency'], item.get('consistency_ci'))} | "
            f"{_cell(json.dumps(item.get('observed_classes', {}), ensure_ascii=False))} |"
        )
    if consistency.get("by_mode"):
        lines.append(
            f"| **合计** | - | - | {consistency.get('failures', 0)} | {consistency.get('matches', 0)} | "
            f"{pct_ci(consistency.get('overall_consistency', 0), consistency.get('overall_ci'))} | - |"
        )
    lines.append("")
    if consistency.get("caveat"):
        lines.append(f"口径：{consistency['caveat']} 这是上限估计，不是独立人工验证。")
        lines.append("")

    assertion_stats = summary.get("assertions") or {}
    lines.append("### 5.3 断言级通过率")
    lines.append("")
    if assertion_stats:
        lines.append(
            f"- Blocking 断言：`{assertion_stats.get('blocking_passed', 0)}/{assertion_stats.get('blocking_total', 0)}` "
            f"通过（`{pct(assertion_stats.get('blocking_pass_rate'))}`）。"
        )
        lines.append(f"- Advisory 断言失败：`{assertion_stats.get('advisory_failures', 0)}` 次（不计入 verdict）。")
        lines.append("")
        lines.append("| 断言类型 | 条数 | 通过率 |")
        lines.append("|---|---:|---:|")
        for name, values in (assertion_stats.get("by_kind") or {}).items():
            lines.append(f"| `{name}` | {values['n']} | {pct(values['pass_rate'])} |")
    lines.append("")

    integrity = (meta.get("oracle_selfcheck") or {}).get("oracle_integrity") or {}
    lines.append("### 5.4 Oracle 完整性（oracle 自己也被测）")
    lines.append("")
    if integrity:
        lines.append(f"- 检查项：`{integrity.get('checks_passed')}/{integrity.get('checks_total')}` 通过；变异体：`{integrity.get('mutants_detected')}/{integrity.get('mutants_total')}` 被抓住。")
        lines.append("")
        lines.append("| 检查 | 结果 | 说明 |")
        lines.append("|---|---|---|")
        for name, item in (integrity.get("checks") or {}).items():
            lines.append(f"| `{name}` | {'通过' if item['passed'] else '失败'} | {_cell(item['detail'])} |")
        lines.append("")
        lines.append("| 注入的 oracle 缺陷 | 是否被抓住 | 命中的检查 |")
        lines.append("|---|---|---|")
        for item in integrity.get("mutants", []):
            lines.append(
                f"| {_cell(item['paper_class'])} | {'是' if item['detected'] else '否'} | "
                f"{_cell(', '.join(item['failed_checks']) or '-')} |"
            )
        lines.append("")
        lines.append(f"依据：{integrity.get('paper', '')}。{integrity.get('caveat', '')}")
    else:
        lines.append("本次没有 oracle 完整性结果。")
    lines.append("")

    lines.append("## 六、正常模式下的误报")
    lines.append("")
    failed_cases = none.get("failed_cases", [])
    if failed_cases:
        lines.append("以下用例在无故障注入时没有全部通过，需要人工复核是用例设计问题还是 Agent 真实缺陷：")
        lines.append("")
        for case_id in failed_cases:
            lines.append(f"- `{case_id}`")
    else:
        lines.append(f"本轮 {meta['cases']}/{meta['cases']} 全部通过，误报率为 0。")
    lines.append("")
    if meta["k"] >= 3:
        lines.append("注意：样本只有 40 条、每族 5 条，置信区间很宽；不要把 100% 读成“绝对稳定”。")
        lines.append("")

    lines.append("## 七、失败样例与证据")
    lines.append("")
    examples = _failure_examples(verdicts)
    if not examples:
        lines.append("本次运行没有失败样例。")
    for index, verdict in enumerate(examples, 1):
        lines.append(f"### {index}. `{verdict.case_id}` / `{verdict.fault_mode}`")
        lines.append("")
        lines.append(f"- 失败类型：`{verdict.failure_class}`（规则优先级 {verdict.confidence:.2f}，非校准概率）")
        lines.append(f"- 归因：{verdict.rationale}")
        if verdict.trace_sha256:
            lines.append(f"- Trace 哈希：`{verdict.trace_sha256[:16]}`")
        failed = [item for item in verdict.assertions if not item.passed]
        for assertion in failed[:3]:
            scope = "（advisory，不计入 verdict）" if assertion.severity != "blocking" else ""
            location = f"，消息 #{assertion.message_index}" if assertion.message_index is not None else ""
            step = f"，工具步 {assertion.evidence_step}" if assertion.evidence_step is not None else ""
            lines.append(f"- 断言 `{assertion.name}`{scope}：{assertion.detail}{location}{step}")
        trace = _load_trace(verdict.trace_path)
        if trace:
            calls = trace.get("tool_calls", [])[-2:]
            if calls:
                lines.append("- 工具轨迹：")
                for call in calls:
                    result = str(call.get("result", ""))[:220]
                    lines.append(f"  - `{call.get('name')}` args=`{json.dumps(call.get('args', {}), ensure_ascii=False)}` → `{result}`")
            output = str(trace.get("output_text", ""))[:220]
            if output:
                lines.append(f"- 最终输出摘录：`{output}`")
        lines.append("")

    lines.append("## 八、局限")
    lines.append("")
    lines.append("- 被测靶子是可控合成环境，故障是注入的，不代表真实生产 Agent 的故障分布。")
    lines.append("- 用例只覆盖教学平台运维的 8 个场景族，每族 5 条；区间估计很宽，未覆盖长周期任务和多 Agent 协作。")
    lines.append("- 失败归因是规则映射，置信度是工程优先级，不是统计校准后的概率；归因一致性是对照注入目录，不是独立人工标注。")
    lines.append("- 成本表与账单不同比例时，预算断言只作告警；token 估算不能替代计费口径。")
    lines.append("- 单模型、单轮实验；扩展到多模型、真实 Agent 和人工双标后，结论才可外推。")
    lines.append("")
    lines.append("## 九、运行元数据")
    lines.append("")
    lines.append("```json")
    lines.append(
        json.dumps(
            {
                "model": meta["model"],
                "temperature": meta.get("temperature", 0.0),
                "cases": meta["cases"],
                "runs": meta["runs"],
                "k": meta["k"],
                "faults": meta["faults"],
                "git_sha": meta.get("git_sha", "unknown"),
                "cases_sha256": meta.get("cases_sha256", "n/a"),
                "duration_s": meta.get("duration_s"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    lines.append("```")
    lines.append("")

    content = "\n".join(lines)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    html = markdown.markdown(content, extensions=["tables", "fenced_code"])
    html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>Agent 验收审计报告</title>
<style>
body{{max-width:980px;margin:40px auto;padding:0 24px;font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;line-height:1.7;color:#1f2328}}
table{{border-collapse:collapse;width:100%;margin:16px 0}}th,td{{border:1px solid #d0d7de;padding:8px 10px;text-align:left}}
th{{background:#f6f8fa}}code{{background:#f6f8fa;padding:2px 5px;border-radius:4px}}
h1,h2{{border-bottom:1px solid #d8dee4;padding-bottom:6px}}
</style></head><body>{html}</body></html>"""
    out.with_suffix(".html").write_text(html, encoding="utf-8")
    return content
