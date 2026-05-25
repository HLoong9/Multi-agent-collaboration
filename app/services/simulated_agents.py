"""Local simulated agents for end-to-end orchestration tests."""

from __future__ import annotations

from app.gateway.schemas import AgentTaskResponse


def simulate_web_initial_scan(payload: dict) -> AgentTaskResponse:
    target_url = payload.get("target_url") or payload.get("root_context", {}).get("target_url", "")
    root_task_id = str(payload.get("root_task_id") or "local")
    response = {
        "task_id": f"sim-web-initial-{root_task_id}",
        "status": "completed",
        "summary": "模拟的 Web 初扫发现了公开源码与联系线索。",
        "findings": [
            {
                "source": "web_pentest",
                "severity": "medium",
                "title": "发现公开源码包",
                "detail": "已发现可供后续代码审计使用的模拟源码归档。",
                "evidence": {"target_url": target_url, "path": "/backup/source.zip"},
            },
            {
                "source": "web_pentest",
                "severity": "info",
                "title": "发现联系邮箱",
                "detail": "已从目标站点提取出示例员工邮箱线索。",
                "evidence": {"emails": ["hr@demotech.local", "admin@demotech.local"]},
            },
        ],
        "artifacts": [
            {
                "artifact_type": "source_snapshot",
                "title": "模拟 Web 源码快照",
                "artifact_ref": f"artifact://{root_task_id}/web/source-snapshot",
                "artifact_metadata": {"target_url": target_url},
            }
        ],
        "suggested_actions": [
            {
                "action_type": "start_code_audit",
                "action_payload": {
                    "reason": "Source snapshot is available for simulated audit.",
                    "requires_approval": True,
                },
            }
        ],
        "errors": [],
    }
    return AgentTaskResponse.model_validate(response)


def simulate_code_audit(payload: dict) -> AgentTaskResponse:
    root_task_id = str(payload.get("root_task_id") or "local")
    artifact_refs = payload.get("artifact_refs") or []
    response = {
        "task_id": f"sim-code-audit-{root_task_id}",
        "status": "completed",
        "summary": "模拟的代码审计发现了管理导出端点和校验线索。",
        "findings": [
            {
                "source": "code_audit",
                "severity": "high",
                "title": "管理导出端点线索",
                "detail": "审计识别出 /api/admin/export 作为可进一步验证的候选端点。",
                "evidence": {"endpoint": "/api/admin/export", "artifact_refs": artifact_refs},
            },
            {
                "source": "code_audit",
                "severity": "medium",
                "title": "校验模式较弱",
                "detail": "模拟中导出端点的输入校验看起来不完整。",
                "evidence": {"file": "controllers/export.py"},
            },
        ],
        "artifacts": [
            {
                "artifact_type": "audit_report",
                "title": "模拟代码审计报告",
                "artifact_ref": f"artifact://{root_task_id}/code/audit-report",
                "artifact_metadata": {"artifact_refs": artifact_refs},
            }
        ],
        "suggested_actions": [
            {
                "action_type": "start_web_reverify",
                "action_payload": {
                    "endpoint": "/api/admin/export",
                    "requires_approval": True,
                },
            }
        ],
        "errors": [],
    }
    return AgentTaskResponse.model_validate(response)


def simulate_web_reverify(payload: dict) -> AgentTaskResponse:
    root_task_id = str(payload.get("root_task_id") or "local")
    response = {
        "task_id": f"sim-web-reverify-{root_task_id}",
        "status": "completed",
        "summary": "模拟的 Web 二次验证已确认代码审计线索在授权范围内。",
        "findings": [
            {
                "source": "web_reverify",
                "severity": "medium",
                "title": "实验环境可达的管理导出端点",
                "detail": "该模拟端点可在授权测试范围内访问。",
                "evidence": {"endpoint": "/api/admin/export", "verified": True},
            }
        ],
        "artifacts": [
            {
                "artifact_type": "web_reverify_log",
                "title": "模拟 Web 二次验证日志",
                "artifact_ref": f"artifact://{root_task_id}/web/reverify-log",
                "artifact_metadata": {},
            }
        ],
        "suggested_actions": [
            {
                "action_type": "start_social_engineering",
                "action_payload": {
                    "reason": "Verified context can enrich the phishing exercise draft.",
                    "requires_approval": True,
                },
            }
        ],
        "errors": [],
    }
    return AgentTaskResponse.model_validate(response)


def simulate_social_engineering(payload: dict) -> AgentTaskResponse:
    root_task_id = str(payload.get("root_task_id") or "local")
    company = payload.get("root_context", {}).get("company") or "DemoTech"
    requested_outputs = set(payload.get("requested_outputs") or [])

    if "send_campaigns" in requested_outputs:
        response = {
            "task_id": f"sim-social-send-{root_task_id}",
            "status": "completed",
            "summary": f"已完成 {company} 的本地发送演练。",
            "findings": [
                {
                    "source": "social_engineering",
                    "severity": "info",
                    "title": "本地发送演练完成",
                    "detail": "仅本地演练的发送步骤已完成，没有对外投递。",
                    "evidence": {"company": company, "delivery_mode": "local_only"},
                }
            ],
            "artifacts": [
                {
                    "artifact_type": "send_receipt",
                    "title": "模拟发送回执",
                    "artifact_ref": f"artifact://{root_task_id}/social/send-receipt",
                    "artifact_metadata": {
                        "company": company,
                        "delivery_mode": "local_only",
                        "sent_count": 2,
                        "targets": ["hr@demotech.local", "admin@demotech.local"],
                    },
                }
            ],
            "suggested_actions": [],
            "errors": [],
        }
        return AgentTaskResponse.model_validate(response)

    if requested_outputs & {"target_analysis", "target_selection_plan"}:
        response = {
            "task_id": f"sim-social-targets-{root_task_id}",
            "status": "completed",
            "summary": f"已完成 {company} 的目标分析。",
            "findings": [
                {
                    "source": "social_engineering",
                    "severity": "info",
                    "title": "已分析目标角色",
                    "detail": "候选演练收件人已按角色和暴露上下文完成分组。",
                    "evidence": {
                        "company": company,
                        "recommended_targets": [
                            {"name": "HR Contact", "email": "hr@demotech.local", "reason": "public contact clue"},
                            {"name": "Admin Contact", "email": "admin@demotech.local", "reason": "admin workflow clue"},
                        ],
                    },
                }
            ],
            "artifacts": [
                {
                    "artifact_type": "target_analysis",
                    "title": "模拟目标分析",
                    "artifact_ref": f"artifact://{root_task_id}/social/target-analysis",
                    "artifact_metadata": {"company": company, "target_count": 2},
                },
                {
                    "artifact_type": "target_selection_plan",
                    "title": "模拟目标选择方案",
                    "artifact_ref": f"artifact://{root_task_id}/social/target-selection-plan",
                    "artifact_metadata": {"company": company},
                },
            ],
            "suggested_actions": [
                {
                    "action_type": "generate_emails",
                    "action_payload": {
                        "requires_approval": True,
                        "reason": "Target analysis should be confirmed before mail draft generation.",
                    },
                }
            ],
            "errors": [],
        }
        return AgentTaskResponse.model_validate(response)

    response = {
        "task_id": f"sim-social-{root_task_id}",
        "status": "completed",
        "summary": f"已为 {company} 准备社会工程草稿。",
        "findings": [
            {
                "source": "social_engineering",
                "severity": "info",
                "title": "演练草稿已准备",
                "detail": "邮件草稿和活动草稿已为本地演练生成。",
                "evidence": {"company": company},
            }
        ],
        "artifacts": [
            {
                "artifact_type": "mail_draft",
                "title": "模拟邮件草稿",
                "artifact_ref": f"artifact://{root_task_id}/social/mail-drafts",
                "artifact_metadata": {
                    "company": company,
                    "drafts": [
                        {
                            "recipient_email": "hr@demotech.local",
                            "subject": f"{company} 演练通知 1",
                            "sender_name": company,
                            "sender_email": f"noreply@{company.lower()}.local",
                            "body": f"您好，\n\n这里是 {company} 的模拟邮件草稿。",
                            "body_html": f"<p>您好，</p><p>这里是 {company} 的模拟邮件草稿。</p>",
                        },
                        {
                            "recipient_email": "admin@demotech.local",
                            "subject": f"{company} 演练通知 2",
                            "sender_name": company,
                            "sender_email": f"noreply@{company.lower()}.local",
                            "body": f"您好，\n\n这里是 {company} 的模拟邮件草稿。",
                            "body_html": f"<p>您好，</p><p>这里是 {company} 的模拟邮件草稿。</p>",
                        },
                    ],
                },
            },
            {
                "artifact_type": "gophish_campaign_draft",
                "title": "模拟 Gophish 活动草稿",
                "artifact_ref": f"artifact://{root_task_id}/social/gophish-campaign",
                "artifact_metadata": {
                    "company": company,
                    "campaign": {
                        "name": f"{company} 模拟活动",
                        "smtp_profile": "local-demo-smtp",
                        "landing_page": "local-demo-page",
                        "target_count": 2,
                    },
                },
            },
        ],
        "suggested_actions": [
            {
                "action_type": "create_gophish_campaign",
                "action_payload": {"requires_approval": True},
            },
            {
                "action_type": "send_link_email",
                "action_payload": {"requires_approval": True},
            },
        ],
        "errors": [],
    }
    return AgentTaskResponse.model_validate(response)
