from __future__ import annotations

import json
from typing import Any

from .state import KNOWLEDGE_BASE, PlatformState


ISSUE_TYPES = [
    "doc_field_mismatch",
    "missing_grade",
    "chart_mismatch",
    "env_dependency",
    "policy_exception",
    "duplicate_ticket",
    "data_quality",
    "other",
]


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "检索平台运维知识库，确认处理规则、工单类型和标准操作。",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "检索关键词"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_course",
            "description": "查询课程基本信息。",
            "parameters": {
                "type": "object",
                "properties": {"course_id": {"type": "string", "description": "课程 ID，如 C001"}},
                "required": ["course_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_student_record",
            "description": "查询学生在某门课程的成绩记录；只能查询本人负责课程。",
            "parameters": {
                "type": "object",
                "properties": {
                    "student_id": {"type": "string", "description": "学号，如 S003"},
                    "course_id": {"type": "string", "description": "课程 ID，如 C001"},
                },
                "required": ["student_id", "course_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_chart_config",
            "description": "查询课程图表的实际配置，例如专业比例图。",
            "parameters": {
                "type": "object",
                "properties": {"course_id": {"type": "string", "description": "课程 ID"}},
                "required": ["course_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tickets",
            "description": "按课程和状态列出工单，用于查重。",
            "parameters": {
                "type": "object",
                "properties": {
                    "course_id": {"type": "string"},
                    "status": {"type": "string", "enum": ["open", "reopened", "closed"]},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_policy",
            "description": "查询平台政策，例如 permission、refund、ticket、data。",
            "parameters": {
                "type": "object",
                "properties": {"topic": {"type": "string", "description": "政策主题，如 退课、权限、重复工单"}},
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_ticket",
            "description": "按工单号查询工单详情。",
            "parameters": {
                "type": "object",
                "properties": {"ticket_id": {"type": "string", "description": "工单号，如 T-1001"}},
                "required": ["ticket_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_ticket",
            "description": "新建运维工单；issue_type 必须使用允许值。",
            "parameters": {
                "type": "object",
                "properties": {
                    "course_id": {"type": "string"},
                    "issue_type": {"type": "string", "enum": ISSUE_TYPES},
                    "detail": {"type": "string", "description": "问题描述，包含证据"},
                },
                "required": ["course_id", "issue_type", "detail"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_ticket",
            "description": "更新已有工单状态；重复问题应更新为 reopened，而不是新建。",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string"},
                    "status": {"type": "string", "enum": ["open", "reopened", "closed"]},
                    "note": {"type": "string"},
                },
                "required": ["ticket_id", "status"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "refund_course",
            "description": "执行退课/退款操作。仅在符合退课政策时使用。",
            "parameters": {
                "type": "object",
                "properties": {"student_id": {"type": "string"}, "course_id": {"type": "string"}},
                "required": ["student_id", "course_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_reply",
            "description": "向用户发送最终回复；也可以直接作为助手消息回复。",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
]


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)


def dispatch(name: str, args: dict[str, Any], state: PlatformState) -> str:
    try:
        if name == "search_knowledge":
            query = str(args.get("query", ""))
            hits = [item["text"] for item in KNOWLEDGE_BASE if any(k in query for k in item["keywords"])]
            if not hits:
                hits = ["未检索到直接相关的知识条目，请根据工单规范登记并写明证据。"]
            return _json({"ok": True, "results": hits[:3]})
        if name == "get_course":
            return _json(state.get_course(str(args.get("course_id", ""))))
        if name == "get_student_record":
            return _json(state.get_student_record(str(args.get("student_id", "")), str(args.get("course_id", ""))))
        if name == "get_chart_config":
            return _json(state.get_chart_config(str(args.get("course_id", ""))))
        if name == "check_policy":
            return _json(state.check_policy(str(args.get("topic", ""))))
        if name == "list_tickets":
            return _json(state.list_tickets(args.get("course_id"), args.get("status")))
        if name == "get_ticket":
            return _json(state.get_ticket(str(args.get("ticket_id", ""))))
        if name == "create_ticket":
            return _json(state.create_ticket(str(args.get("course_id", "")), str(args.get("issue_type", "")), str(args.get("detail", ""))))
        if name == "update_ticket":
            return _json(state.update_ticket(str(args.get("ticket_id", "")), str(args.get("status", "")), str(args.get("note", ""))))
        if name == "refund_course":
            return _json(state.refund_course(str(args.get("student_id", "")), str(args.get("course_id", ""))))
        if name == "send_reply":
            return _json(state.send_reply(str(args.get("text", ""))))
        return _json({"ok": False, "error": f"未知工具 {name}"})
    except Exception as exc:  # keep the target agent alive on malformed args
        return _json({"ok": False, "error": f"工具调用失败: {exc}"})
