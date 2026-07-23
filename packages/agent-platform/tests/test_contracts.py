from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import ValidationError
import pytest

from agent_platform.core import (
    ConversationMessage,
    ConversationRole,
    EventExtensionEnvelope,
    PresentationEnvelope,
)
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


def test_conversation_message_keeps_versioned_product_presentations_opaque() -> None:
    presentation = PresentationEnvelope(
        kind="example.product-results",
        schema_version=1,
        payload={"parts": [{"type": "product_result", "payload": {"id": "1"}}]},
    )
    message = ConversationMessage(
        id=uuid4(),
        thread_id=uuid4(),
        run_id=uuid4(),
        role=ConversationRole.assistant,
        content="已处理",
        presentation=presentation,
        created_at=datetime.now(UTC),
    )

    assert message.presentation == presentation
    assert message.presentation.payload["parts"][0]["payload"] == {"id": "1"}


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
            created_at=datetime.now(UTC),
        )


def test_event_extension_requires_identity_and_version() -> None:
    extension = EventExtensionEnvelope(
        kind="example.event",
        schema_version=1,
        payload={"value": 1},
    )

    assert extension.payload == {"value": 1}
    with pytest.raises(ValidationError):
        EventExtensionEnvelope(kind="", schema_version=1, payload={})
    with pytest.raises(ValidationError):
        EventExtensionEnvelope(kind="example.event", schema_version=0, payload={})
