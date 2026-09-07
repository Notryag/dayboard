from __future__ import annotations

from dataclasses import dataclass
import json
from threading import Lock

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import messages_to_dict
from north import normalize_token_usage

from limits import parse
from limits.storage import MemoryStorage, storage_from_string
from limits.strategies import FixedWindowRateLimiter

from dayboard.config import Settings, get_settings
from agent_platform.core import UserContext


class ProviderBudgetExceeded(RuntimeError):
    def __init__(self, budget_type: str, limit: str) -> None:
        super().__init__(f"Provider {budget_type} budget exceeded: {limit}")
        self.budget_type = budget_type
        self.limit = limit


@dataclass(frozen=True)
class ProviderBudgetEstimate:
    request_units: int = 1
    token_units: int = 0


def estimate_prompt_tokens(text: str) -> int:
    """Reserve by UTF-8 bytes instead of undercounting Chinese as len(text) / 4."""

    normalized = text.strip()
    if not normalized:
        return 1
    return max(1, len(normalized.encode("utf-8")))


class ProviderBudgetGuard:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        if self.settings.provider_budget_storage_url == "memory://":
            storage = MemoryStorage()
        else:
            storage = storage_from_string(self.settings.effective_provider_budget_storage_url)
        self.limiter = FixedWindowRateLimiter(storage)
        self.request_limit = parse(self.settings.provider_budget_request_limit)
        self.token_limit = parse(self.settings.provider_budget_token_limit)

    def estimate(self, *, input_text: str) -> ProviderBudgetEstimate:
        return ProviderBudgetEstimate(token_units=estimate_prompt_tokens(input_text))

    def check(
        self,
        *,
        context: UserContext,
        model_name: str,
        estimate: ProviderBudgetEstimate,
    ) -> None:
        if not self.settings.provider_budget_enabled:
            return

        key = f"user:{context.user_id}:model:{model_name}"
        if estimate.request_units and not self.limiter.hit(
            self.request_limit, f"provider-requests:{key}", cost=estimate.request_units
        ):
            raise ProviderBudgetExceeded("request", str(self.request_limit))
        if estimate.token_units and not self.limiter.hit(
            self.token_limit, f"provider-tokens:{key}", cost=estimate.token_units
        ):
            raise ProviderBudgetExceeded("token", str(self.token_limit))

    def reconcile_actual(
        self,
        *,
        context: UserContext,
        model_name: str,
        estimate: ProviderBudgetEstimate,
        actual_tokens: int,
    ) -> int:
        """Charge actual usage above the pre-call reservation.

        Fixed-window storage cannot safely refund a Run that settles after its
        admission window expires, so lower-than-estimated usage remains reserved.
        """

        if not self.settings.provider_budget_enabled:
            return 0
        additional_tokens = max(0, actual_tokens - estimate.token_units)
        if additional_tokens == 0:
            return 0
        key = f"user:{context.user_id}:model:{model_name}"
        self.limiter.hit(
            self.token_limit,
            f"provider-tokens:{key}",
            cost=additional_tokens,
        )
        return additional_tokens


class RunModelBudget(BaseCallbackHandler):
    """One Run's provider-call reservations, including summarization calls.

    Registered on the invocation config, so North and LangChain propagate it to
    both the lead model and the summary model. No prompt content is persisted.
    """

    raise_error = True
    run_inline = True

    def __init__(
        self,
        guard: ProviderBudgetGuard,
        context: UserContext,
        model_name: str,
        admission: ProviderBudgetEstimate,
    ) -> None:
        self.guard = guard
        self.context = context
        self.model_name = model_name
        self.max_calls = guard.settings.agent_max_model_calls
        self.max_tokens = guard.settings.agent_max_run_tokens
        self.max_output = guard.settings.agent_max_output_tokens
        self.calls = 0
        self.tokens = 0
        self.reservation = admission
        self.pending: dict[object, int] = {}
        self.rejected: Exception | None = None
        self.lock = Lock()

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs) -> None:
        params = kwargs.get("invocation_params") or {}
        # Include tool schemas and the complete messages actually sent to the model.
        payload = {
            "messages": [messages_to_dict(batch) for batch in messages],
            "tools": params.get("tools", []),
            "response_format": params.get("response_format"),
        }
        estimate = estimate_prompt_tokens(json.dumps(payload, ensure_ascii=False, default=str))
        estimate += self.max_output
        with self.lock:
            if self.rejected is not None:
                raise self.rejected
            try:
                if self.calls >= self.max_calls:
                    raise ProviderBudgetExceeded("run_requests", str(self.max_calls))
                if self.tokens + estimate > self.max_tokens:
                    raise ProviderBudgetExceeded("run_tokens", str(self.max_tokens))
                # The admission already reserved the first request and input text.
                extra = (
                    max(0, estimate - self.reservation.token_units) if not self.calls else estimate
                )
                self.guard.check(
                    context=self.context,
                    model_name=self.model_name,
                    estimate=ProviderBudgetEstimate(
                        request_units=0 if not self.calls else 1, token_units=extra
                    ),
                )
            except Exception as exc:
                self.rejected = exc
                raise
            self.reservation = ProviderBudgetEstimate(
                request_units=max(1, self.calls + 1),
                token_units=self.reservation.token_units + extra,
            )
            self.calls += 1
            self.tokens += estimate
            self.pending[run_id] = estimate

    def on_llm_end(self, response, *, run_id, **kwargs) -> None:
        usages = [
            normalize_token_usage(
                getattr(generation.message, "usage_metadata", None),
                getattr(generation.message, "response_metadata", None),
            )
            for batch in response.generations
            for generation in batch
            if hasattr(generation, "message")
        ]
        response_usage = normalize_token_usage(response.llm_output)
        actual = sum(usage.total_tokens for usage in usages if usage is not None)
        if not any(usage is not None for usage in usages) and response_usage is not None:
            actual = response_usage.total_tokens
        with self.lock:
            reserved = self.pending.pop(run_id, 0)
            if not reserved:
                return
            # Keep reservations when provider usage is unknown or a call fails.
            if actual:
                self.tokens += actual - reserved
            if actual > reserved:
                self.guard.reconcile_actual(
                    context=self.context,
                    model_name=self.model_name,
                    estimate=ProviderBudgetEstimate(token_units=reserved),
                    actual_tokens=actual,
                )
                self.reservation = ProviderBudgetEstimate(
                    request_units=self.reservation.request_units,
                    token_units=self.reservation.token_units + actual - reserved,
                )
