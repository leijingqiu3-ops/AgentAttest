from __future__ import annotations

import re

# Heuristic patterns, not a trained classifier. They catch the common
# "ignore previous instructions / delete everything" family and nothing more.
PATTERNS: list[tuple[str, str]] = [
    ("override_rules", r"(忽略|无视|跳过|忘掉).{0,10}(之前|以上|前面|系统).{0,8}(规则|指令|提示|限制)"),
    ("override_rules_en", r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|rules?)"),
    ("system_prompt", r"(system\s*prompt|开发者模式|developer\s*mode|jailbreak|DAN)"),
    ("destructive", r"(删除|清空|格式化|rm\s+-rf).{0,10}(所有|全部|整个).{0,6}(文件|数据|库|目录)"),
]


def scan_untrusted_input(text: str) -> list[str]:
    """Return the labels of injection patterns found in untrusted user text."""
    if not text:
        return []
    flags: list[str] = []
    for label, pattern in PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            flags.append(label)
    return flags