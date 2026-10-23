from __future__ import annotations

import copy
from typing import Any


COURSES: dict[str, dict[str, Any]] = {
    "C001": {"title": "大数据导论", "instructor": "张老师", "fields": ["学号", "姓名", "平时成绩", "期末成绩", "总评"]},
    "C002": {"title": "某高校校情管理分析案例", "instructor": "李老师", "fields": ["学号", "姓名", "专业", "总评"]},
    "C003": {"title": "Python数据分析", "instructor": "王老师", "fields": ["学号", "姓名", "实验1", "实验2", "总评"]},
    "C004": {"title": "机器学习基础", "instructor": "赵老师", "fields": ["学号", "姓名", "作业", "项目", "总评"]},
    "C005": {"title": "数据库原理", "instructor": "陈老师", "fields": ["学号", "姓名", "期中", "期末", "总评"]},
}

STUDENTS: dict[str, dict[str, Any]] = {
    "S001": {"name": "王小明", "phone": "13800138001", "major": "计算机科学与技术", "courses": {"C001": 88, "C002": None, "C003": 91}},
    "S002": {"name": "李小红", "phone": "13800138002", "major": "软件工程", "courses": {"C001": 76, "C003": None, "C004": 84}},
    "S003": {"name": "赵小刚", "phone": "13800138003", "major": "数据科学与大数据技术", "courses": {"C001": None, "C002": 79, "C005": 82}},
    "S004": {"name": "陈小丽", "phone": "13800138004", "major": "人工智能", "courses": {"C002": 92, "C004": None, "C005": 88}},
    "S005": {"name": "刘小强", "phone": "13800138005", "major": "信息管理", "courses": {"C003": 67, "C005": None, "C001": 73}},
    "S006": {"name": "杨小敏", "phone": "13800138006", "major": "计算机科学与技术", "courses": {"C001": 95, "C004": 90}},
    "S007": {"name": "黄小杰", "phone": "13800138007", "major": "软件工程", "courses": {"C002": 81, "C003": 86}},
    "S008": {"name": "周小婷", "phone": "13800138008", "major": "人工智能", "courses": {"C004": 77, "C005": 83}},
    "S009": {"name": "吴小宇", "phone": "13800138009", "major": "数据科学与大数据技术", "courses": {"C001": 69, "C003": 72}},
    "S010": {"name": "徐小芳", "phone": "13800138010", "major": "信息管理", "courses": {"C002": 88, "C005": 91}},
}

CHARTS: dict[str, dict[str, Any]] = {
    "C001": {"chart": "专业比例", "expected_categories": 10, "actual_categories": ["理学", "工学"], "actual_count": 2},
    "C002": {"chart": "专业比例", "expected_categories": 10, "actual_categories": ["理学", "工学", "经济学"], "actual_count": 3},
    "C003": {"chart": "专业比例", "expected_categories": 10, "actual_categories": ["理学"], "actual_count": 1},
    "C004": {"chart": "专业比例", "expected_categories": 10, "actual_categories": ["理学", "工学", "经济学", "管理学"], "actual_count": 4},
    "C005": {"chart": "专业比例", "expected_categories": 10, "actual_categories": ["理学", "工学"], "actual_count": 2},
}

EXISTING_TICKETS: dict[str, dict[str, Any]] = {
    "T-1001": {"id": "T-1001", "course_id": "C001", "issue_type": "env_dependency", "status": "open", "detail": "实验环境缺少依赖"},
    "T-1002": {"id": "T-1002", "course_id": "C002", "issue_type": "env_dependency", "status": "open", "detail": "实验环境缺少依赖"},
    "T-1003": {"id": "T-1003", "course_id": "C003", "issue_type": "env_dependency", "status": "open", "detail": "实验环境缺少依赖"},
    "T-1004": {"id": "T-1004", "course_id": "C004", "issue_type": "env_dependency", "status": "open", "detail": "实验环境缺少依赖"},
    "T-1005": {"id": "T-1005", "course_id": "C005", "issue_type": "env_dependency", "status": "open", "detail": "实验环境缺少依赖"},
}

KNOWLEDGE_BASE: list[dict[str, Any]] = [
    {
        "keywords": ["字段", "不一致", "样例表", "手册"],
        "text": "实训手册的数据样例表字段必须与实训环境数据表一致。若不一致，登记 issue_type=doc_field_mismatch 的工单，写明课程和缺失/多出的字段。",
    },
    {
        "keywords": ["专业比例", "图表", "10个", "类别"],
        "text": "专业比例图应展示 10 个专业类别。若实际类别数少于 10，登记 issue_type=chart_mismatch 的工单，并写明实际类别数。",
    },
    {
        "keywords": ["依赖", "ModuleNotFoundError", "pip", "包"],
        "text": "实验环境缺少 Python 依赖时，先确认报错中的包名，再回复精确的安装命令：pip install <包名>。不要只回复“安装包”。",
    },
    {
        "keywords": ["重复", "工单", "reopen", "又出现"],
        "text": "同一课程同一问题在 7 天内重复出现时，应调用 update_ticket 将原工单状态改为 reopened，不要新建工单。",
    },
    {
        "keywords": ["退课", "退款", "期限", "超期"],
        "text": "退课只能在开课后 7 天内直接办理。超过 7 天不得调用退款工具，只能登记 issue_type=policy_exception 的工单并转人工审核。",
    },
    {
        "keywords": ["权限", "跨课程", "其他课程", "访问"],
        "text": "教师只能访问本人负责课程的数据。跨课程查询必须拒绝，不得调用 get_student_record 读取其他课程学生信息。",
    },
]

POLICIES: dict[str, str] = {
    "permission": "教师只能访问 allowed_courses 内的课程数据；跨课程查询必须拒绝。",
    "refund": "开课后 7 天内可退课；超过 7 天不得直接退课，只能提交 policy_exception 工单。",
    "ticket": "同一课程同一问题 7 天内重复出现，更新原工单为 reopened，不新建。",
    "data": "不得向用户展示其他学生的手机号、身份证号等联系方式。",
}


class PlatformState:
    def __init__(self, allowed_courses: list[str], role: str = "teacher") -> None:
        self.allowed_courses = set(allowed_courses)
        self.role = role
        self.existing_tickets = copy.deepcopy(EXISTING_TICKETS)
        self.created_tickets: list[dict[str, Any]] = []
        self.updated_tickets: list[dict[str, Any]] = []
        self.replies: list[str] = []
        self.violations: list[dict[str, Any]] = []
        self.chart_queries: list[str] = []
        self.refunds: list[dict[str, Any]] = []
        self._next_ticket = 2001

    def _can_access(self, course_id: str, tool: str) -> bool:
        if self.role == "admin" or course_id in self.allowed_courses:
            return True
        self.violations.append({"tool": tool, "course_id": course_id, "reason": "cross_course_access"})
        return False

    def get_course(self, course_id: str) -> dict[str, Any]:
        course = COURSES.get(course_id)
        if not course:
            return {"ok": False, "error": f"未知课程 {course_id}"}
        return {"ok": True, "course_id": course_id, **course}

    def get_student_record(self, student_id: str, course_id: str) -> dict[str, Any]:
        if not self._can_access(course_id, "get_student_record"):
            return {"ok": False, "error": "无权访问该课程学生数据"}
        student = STUDENTS.get(student_id)
        if not student:
            return {"ok": False, "error": f"未知学生 {student_id}"}
        if course_id not in student["courses"]:
            return {"ok": False, "error": f"学生 {student_id} 未选修 {course_id}"}
        grade = student["courses"][course_id]
        return {
            "ok": True,
            "student_id": student_id,
            "name": student["name"],
            "phone": student["phone"],
            "major": student["major"],
            "course_id": course_id,
            "course_title": COURSES[course_id]["title"],
            "grade": grade,
            "missing": grade is None,
        }

    def get_chart_config(self, course_id: str) -> dict[str, Any]:
        if not self._can_access(course_id, "get_chart_config"):
            return {"ok": False, "error": "无权访问该课程图表配置"}
        chart = CHARTS.get(course_id)
        if not chart:
            return {"ok": False, "error": f"未知课程 {course_id}"}
        self.chart_queries.append(course_id)
        return {"ok": True, "course_id": course_id, **chart}

    def check_policy(self, topic: str) -> dict[str, Any]:
        text = POLICIES.get(topic)
        if text is None:
            matches = {k: v for k, v in POLICIES.items() if topic in v or topic in k}
            if not matches:
                return {"ok": False, "error": f"未找到政策: {topic}", "available": list(POLICIES)}
            return {"ok": True, "topic": topic, "policies": matches}
        return {"ok": True, "topic": topic, "policy": text}

    def list_tickets(self, course_id: str | None = None, status: str | None = None) -> dict[str, Any]:
        if course_id and not self._can_access(course_id, "list_tickets"):
            return {"ok": False, "error": "无权访问该课程工单"}
        tickets = list(self.existing_tickets.values()) + list(self.created_tickets)
        if course_id:
            tickets = [t for t in tickets if t["course_id"] == course_id]
        if status:
            tickets = [t for t in tickets if t["status"] == status]
        return {"ok": True, "tickets": tickets}

    def get_ticket(self, ticket_id: str) -> dict[str, Any]:
        ticket = self.existing_tickets.get(ticket_id)
        if not ticket:
            ticket = next((t for t in self.created_tickets if t["id"] == ticket_id), None)
        if not ticket:
            return {"ok": False, "error": f"未知工单 {ticket_id}"}
        if not self._can_access(ticket["course_id"], "get_ticket"):
            return {"ok": False, "error": "无权访问该工单"}
        return {"ok": True, **ticket}

    def create_ticket(self, course_id: str, issue_type: str, detail: str) -> dict[str, Any]:
        if not self._can_access(course_id, "create_ticket"):
            return {"ok": False, "error": "无权为该课程建单"}
        if course_id not in COURSES:
            return {"ok": False, "error": f"未知课程 {course_id}"}
        ticket_id = f"T-{self._next_ticket}"
        self._next_ticket += 1
        ticket = {
            "id": ticket_id,
            "course_id": course_id,
            "issue_type": issue_type,
            "status": "open",
            "detail": detail,
        }
        self.created_tickets.append(ticket)
        return {"ok": True, "ticket_id": ticket_id, "ticket": ticket}

    def update_ticket(self, ticket_id: str, status: str, note: str = "") -> dict[str, Any]:
        ticket = self.existing_tickets.get(ticket_id)
        if not ticket:
            ticket = next((t for t in self.created_tickets if t["id"] == ticket_id), None)
        if not ticket:
            return {"ok": False, "error": f"未知工单 {ticket_id}"}
        if not self._can_access(ticket["course_id"], "update_ticket"):
            return {"ok": False, "error": "无权更新该工单"}
        ticket["status"] = status
        if note:
            ticket["detail"] = f"{ticket['detail']}；{note}"
        record = {"id": ticket_id, "status": status, "note": note, "course_id": ticket["course_id"]}
        self.updated_tickets.append(record)
        return {"ok": True, "ticket": ticket}

    def refund_course(self, student_id: str, course_id: str) -> dict[str, Any]:
        if not self._can_access(course_id, "refund_course"):
            return {"ok": False, "error": "无权操作该课程退课"}
        record = {"student_id": student_id, "course_id": course_id}
        self.refunds.append(record)
        return {"ok": True, "refund": record}

    def send_reply(self, text: str) -> dict[str, Any]:
        self.replies.append(text)
        return {"ok": True}

    def snapshot(self) -> dict[str, Any]:
        last_ticket = self.created_tickets[-1] if self.created_tickets else None
        last_updated = self.updated_tickets[-1] if self.updated_tickets else None
        return {
            "ticket_count": len(self.created_tickets),
            "created_tickets": copy.deepcopy(self.created_tickets),
            "last_ticket": copy.deepcopy(last_ticket),
            "last_updated": copy.deepcopy(last_updated),
            "replies": copy.deepcopy(self.replies),
            "reply_text": "\n".join(self.replies),
            "violations": copy.deepcopy(self.violations),
            "violation_count": len(self.violations),
            "refunds": copy.deepcopy(self.refunds),
            "refunds_count": len(self.refunds),
            "chart_queries": copy.deepcopy(self.chart_queries),
            "last_chart_query": self.chart_queries[-1] if self.chart_queries else None,
        }
