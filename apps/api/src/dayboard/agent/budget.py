from __future__ import annotations

from dataclasses import dataclass

from limits import parse
from limits.storage import MemoryStorage, storage_from_string
from limits.strategies import FixedWindowRateLimiter

from dayboard.config import Settings, get_settings
from agent_platform.identity import TenantContext


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
    """Cheap conservative estimate used before provider-specific tokenizers land."""

    normalized = text.strip()
    if not normalized:
        return 1
    return max(1, (len(normalized) + 3) // 4)


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
        context: TenantContext,
        model_name: str,
        estimate: ProviderBudgetEstimate,
    ) -> None:
        if not self.settings.provider_budget_enabled:
            return

        key = f"tenant:{context.tenant_id}:user:{context.user_id}:model:{model_name}"
        if not self.limiter.hit(self.request_limit, f"provider-requests:{key}", cost=estimate.request_units):
            raise ProviderBudgetExceeded("request", str(self.request_limit))
        if not self.limiter.hit(self.token_limit, f"provider-tokens:{key}", cost=estimate.token_units):
            raise ProviderBudgetExceeded("token", str(self.token_limit))

    def reconcile_actual(
        self,
        *,
        context: TenantContext,
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
        key = f"tenant:{context.tenant_id}:user:{context.user_id}:model:{model_name}"
        self.limiter.hit(
            self.token_limit,
            f"provider-tokens:{key}",
            cost=additional_tokens,
        )
        return additional_tokens
