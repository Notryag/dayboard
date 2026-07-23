from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import ValidationError
import pytest

from agent_platform.core import ConversationMessage, ConversationRole
from agent_platform.core import TenantContext
from agent_platform.core import AgentRunEvent, AgentRunEventCategory


def test_tenant_context_is_trusted_immutable_data() -> None:
    context = TenantContext(
        tenant_id=uuid4(),
        user_id=uuid4(),
        timezone="Asia/Shanghai",
        locale="zh-CN",
    )

    with pytest.raises(FrozenInstanceError):
        context.timezone = "UTC"  # type: ignore[misc]


def test_conversation_message_keeps_product_artifacts_opaque() -> None:
    message = ConversationMessage(
        id=uuid4(),
        thread_id=uuid4(),
        run_id=uuid4(),
        role=ConversationRole.assistant,
        content="已处理",
        message_metadata={"parts": [{"type": "product_result", "payload": {"id": "1"}}]},
        created_at=datetime.now(UTC),
    )

    assert message.message_metadata["parts"][0]["payload"] == {"id": "1"}


def test_run_event_rejects_empty_event_type() -> None:
    with pytest.raises(ValidationError):
        AgentRunEvent(
            id=uuid4(),
            tenant_id=uuid4(),
            run_id=uuid4(),
            seq=1,
            event_type="",
            category=AgentRunEventCategory.lifecycle,
            content=None,
            event_metadata={},
            created_at=datetime.now(UTC),
        )
