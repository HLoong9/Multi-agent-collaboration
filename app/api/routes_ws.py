"""WebSocket routes for the orchestrator console."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.ws import (
    AgentCallPlannedWsEvent,
    AgentProgressWsEvent,
    AgentResultWsEvent,
    ApprovalDecisionWsMessage,
    ApprovalRequiredWsEvent,
    ErrorWsEvent,
    ResultSnapshotWsEvent,
    ThinkingWsEvent,
    UserInputWsMessage,
    parse_client_ws_message,
)
from app.schemas.tasks import TaskCreateRequest
from app.services.agent_task_router import AgentTaskRouter, AgentTaskRouterError
from app.services.chat_intent_router import ChatIntentRouter
from app.services.result_snapshot import ResultSnapshotBuilder
from app.services.suggested_action_manager import SuggestedActionManager
from app.services.workflow_service import WorkflowService
from app.llm.client import LLMClient, LLMClientError
from app.storage.database import AsyncSessionLocal, get_db_session
from app.storage.repository import OrchestratorRepository

router = APIRouter(tags=["ws"])


class WsChatHandler:
    CHAT_SYSTEM_PROMPT = (
        "你是 Orchestrator 多 Agent 安全演练平台的调度助手。"
        "你可以回答关于平台功能、Agent 类型、使用方法的问题，也可以进行日常闲聊。"
        "平台包含三个 Agent：Web 渗透（web_pentest）、代码审计（code_audit）、社工钓鱼（social_engineering）。"
        "当用户需要执行具体安全任务时，建议他们用关键词触发，例如'代码审计'、'web渗透'、'钓鱼'等。"
        "回答要简洁，用中文。"
    )
    FALLBACK_REPLY = "我可以帮你调度多 Agent 流程，你可以尝试说'代码审计'、'web渗透'或'钓鱼'来启动对应 Agent。"

    def __init__(
        self,
        repo: OrchestratorRepository | None = None,
        intent_router: ChatIntentRouter | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        self.repo = repo
        self.intent_router = intent_router or ChatIntentRouter()
        self.llm_client = llm_client
        self.pending_actions: dict[str, dict[str, Any]] = {}

    async def handle_user_input(self, payload: UserInputWsMessage) -> list[dict[str, Any]]:
        intent = self.intent_router.detect(payload.content)
        events: list[dict[str, Any]] = [
            ThinkingWsEvent(message="正在识别任务意图").model_dump(mode="json")
        ]
        if self.repo is None:
            return await self._preview_events(intent, events, payload.content)

        if intent.intent_type == "manual_agent" and intent.agent_type:
            root_task_id = await self._ensure_root_task(payload, intent.target_url)
            planned_payload = {"target_url": intent.target_url} if intent.target_url else {}
            events.append(AgentCallPlannedWsEvent(
                agent_type=intent.agent_type,
                reason=f"用户指定调用 {intent.agent_type}",
                payload=planned_payload,
            ).model_dump(mode="json"))
            action_id = str(uuid.uuid4())
            action = {
                "id": action_id,
                "action_id": action_id,
                "root_task_id": str(root_task_id),
                "source_agent": "orchestrator",
                "target_agent": intent.agent_type,
                "action_type": "start_manual_agent",
                "status": "pending",
                "reason": f"是否启动 {intent.agent_type} 任务",
                "risk_level": "medium",
                "risk_text": "启动后将调用对应Agent执行任务。",
                "payload_preview": planned_payload,
                "user_text": payload.content,
            }
            self.pending_actions[action_id] = action
            events.append(ApprovalRequiredWsEvent(approval=action).model_dump(mode="json"))
            return events
        if intent.intent_type == "auto_workflow":
            task = await WorkflowService(self.repo).create_and_start(
                TaskCreateRequest(
                    target_url=intent.target_url or "http://web1.demotech.local",
                    exercise_goal=payload.content,
                    auth_scope={
                        "allowed_targets": ["http://web1.demotech.local", "http://web2.demotech.local"],
                        "allowed_domains": ["web1.demotech.local", "web2.demotech.local"],
                    },
                    created_by="operator",
                )
            )
            events.append({"type": "assistant_chunk", "content": "自动化流程已创建并推进到当前可执行状态。"})
            events.append(ResultSnapshotWsEvent(data=await ResultSnapshotBuilder(self.repo).build(task.id)).model_dump(mode="json"))
            return events
        reply = await self._chat_reply(payload.content)
        events.append({"type": "assistant_chunk", "content": reply})
        return events

    async def handle_approval_decision(self, payload: ApprovalDecisionWsMessage) -> list[dict[str, Any]]:
        if self.repo is None:
            return [ErrorWsEvent(message="approval handling unavailable").model_dump(mode="json")]
        action = self.pending_actions.get(payload.action_id)
        if action is None:
            return await self._handle_workflow_approval_decision(payload)
        action["status"] = payload.decision
        if payload.decision != "approved":
            return [{"type": "assistant_chunk", "content": f"已记录确认结果：{payload.decision}"}]
        target_agent = action.get("target_agent")
        if not target_agent:
            return [ErrorWsEvent(message="待确认动作缺少目标 Agent").model_dump(mode="json")]
        root_task_id = action.get("root_task_id")
        events = [
            {"type": "assistant_chunk", "content": f"正在执行 {target_agent}。"},
            AgentProgressWsEvent(agent_type=target_agent, status="running", message="已确认启动任务").model_dump(mode="json"),
            AgentProgressWsEvent(agent_type=target_agent, status="running", message="正在构建Agent请求参数").model_dump(mode="json"),
            AgentProgressWsEvent(agent_type=target_agent, status="running", message="正在提交Agent任务").model_dump(mode="json"),
            AgentProgressWsEvent(agent_type=target_agent, status="running", message="正在等待Agent返回结果").model_dump(mode="json"),
        ]
        try:
            task = await self.repo.get_root_task(uuid.UUID(str(root_task_id)))
            task_scope = getattr(task, "auth_scope", None) or {}
            result = await AgentTaskRouter(self.repo).run_manual_agent(
                root_task_id=uuid.UUID(str(root_task_id)),
                agent_type=target_agent,
                text=action.get("user_text") or action.get("action_type") or target_agent,
                auth_scope=task_scope,
                created_by="operator",
            )
        except AgentTaskRouterError as exc:
            events.append(ErrorWsEvent(message=str(exc)).model_dump(mode="json"))
            return events
        response_data = result.response.model_dump(mode="json")
        events.append(AgentProgressWsEvent(agent_type=target_agent, status="completed", message="已收到Agent返回结果，正在整理展示").model_dump(mode="json"))
        events.append(AgentResultWsEvent(agent_type=target_agent, data=response_data).model_dump(mode="json"))
        events.append(ResultSnapshotWsEvent(data=await ResultSnapshotBuilder(self.repo).build(root_task_id)).model_dump(mode="json"))
        return events

    async def _handle_workflow_approval_decision(self, payload: ApprovalDecisionWsMessage) -> list[dict[str, Any]]:
        try:
            approval_id = uuid.UUID(payload.action_id)
        except ValueError:
            return [ErrorWsEvent(message="未找到待确认动作").model_dump(mode="json")]

        approval = await self.repo.get_approval(approval_id)
        if approval is None:
            return [ErrorWsEvent(message="未找到待确认动作").model_dump(mode="json")]
        if getattr(approval, "status", "") != "pending":
            return [ErrorWsEvent(message="该确认动作已处理").model_dump(mode="json")]
        if payload.decision == "deferred":
            return [{"type": "assistant_chunk", "content": "已记录确认结果：deferred"}]

        status = "approved" if payload.decision == "approved" else "rejected"
        updated = await self.repo.decide_approval(
            approval_id,
            status=status,
            decided_by="operator",
            decision_comment=f"{status} in websocket",
        )
        if updated is None:
            return [ErrorWsEvent(message="未找到待确认动作").model_dump(mode="json")]

        await self.repo.create_event(
            root_task_id=updated.root_task_id,
            event_type="approval_decided",
            message=f"approval {status}",
            payload={"approval_id": str(updated.id), "decision": payload.decision, "source": "websocket"},
        )
        asyncio.create_task(self._resume_workflow_after_approval_background(updated.id))
        reply = "已批准当前动作，流程继续。" if status == "approved" else "已拒绝当前动作，流程已停止。"
        if status == "approved":
            reply = "已批准当前动作，流程正在后台执行。页面会继续刷新任务状态。"
        return [
            {"type": "assistant_chunk", "content": reply},
            ResultSnapshotWsEvent(data=await ResultSnapshotBuilder(self.repo).build(updated.root_task_id)).model_dump(mode="json"),
        ]

    async def _resume_workflow_after_approval_background(self, approval_id: uuid.UUID) -> None:
        async with AsyncSessionLocal() as session:
            await WorkflowService(OrchestratorRepository(session)).resume_after_approval(approval_id)

    async def _ensure_root_task(self, payload: UserInputWsMessage, target_url: str | None):
        if payload.root_task_id:
            return uuid.UUID(payload.root_task_id)
        task = await self.repo.create_root_task(
            target_url=target_url or "",
            exercise_goal=payload.content,
            auth_scope={"allowed_hosts": ["web1.demotech.local", "web2.demotech.local"]},
            created_by="operator",
        )
        return task.id

    async def _chat_reply(self, user_message: str) -> str:
        if self.llm_client is None:
            return self.FALLBACK_REPLY
        try:
            return await self.llm_client.chat_text(
                system_prompt=self.CHAT_SYSTEM_PROMPT,
                user_message=user_message,
            )
        except LLMClientError:
            return self.FALLBACK_REPLY

    async def _preview_events(
        self, intent, events: list[dict[str, Any]], user_message: str,
    ) -> list[dict[str, Any]]:
        if intent.intent_type == "manual_agent" and intent.agent_type:
            events.append(AgentCallPlannedWsEvent(
                agent_type=intent.agent_type,
                reason=f"用户指定调用 {intent.agent_type}",
                payload={"target_url": intent.target_url} if intent.target_url else {},
            ).model_dump(mode="json"))
            return events
        reply = await self._chat_reply(user_message)
        events.append({"type": "assistant_chunk", "content": reply})
        return events


def get_ws_chat_handler(session: AsyncSession = Depends(get_db_session)) -> WsChatHandler:
    return WsChatHandler(
        repo=OrchestratorRepository(session),
        llm_client=LLMClient(),
    )


@router.websocket("/ws/orchestrator/{session_id}")
async def orchestrator_ws(
    websocket: WebSocket,
    session_id: str,
    handler: WsChatHandler = Depends(get_ws_chat_handler),
) -> None:
    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_json()
            try:
                message = parse_client_ws_message(raw)
                if isinstance(message, UserInputWsMessage):
                    events = await handler.handle_user_input(message)
                else:
                    events = await handler.handle_approval_decision(message)
                for event in events:
                    await websocket.send_json(event)
            except Exception as exc:
                await websocket.send_json(
                    ErrorWsEvent(message=str(exc), payload={"session_id": session_id}).model_dump(mode="json")
                )
    except WebSocketDisconnect:
        return
