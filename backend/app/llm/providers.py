"""One OpenAI-compatible client, several free-tier providers, tried in order.

Groq, Cerebras and Gemini all speak the OpenAI chat-completions API, so the advisor talks to one interface and a
rate limit on one provider simply moves the call to the next. The provider order and models come from .env:

    ADVISOR_PROVIDER_CHAIN=groq,cerebras,mistral,openrouter,gemini      providers without an API key are skipped
    ADVISOR_MODEL_GROQ=openai/gpt-oss-120b           ADVISOR_MODEL_CEREBRAS=gpt-oss-120b     GEMINI_MODEL=...
    ADVISOR_MODEL_MISTRAL=mistral-small-latest       ADVISOR_MODEL_OPENROUTER=openai/gpt-oss-120b:free
    ADVISOR_REASONING_EFFORT=medium                  gpt-oss models: medium = reliable tool calls in Hindi; low skipped them
    ADVISOR_MAX_WAIT_S=20                            if every provider is rate-limited, wait this long at most

Only the KYC vision step is provider-specific (Gemini, see kyc/extract.py).
"""
import logging
import os
import time
from dataclasses import dataclass, field

from openai import APIConnectionError, APIStatusError, BadRequestError, OpenAI, RateLimitError

from .. import config  # noqa: F401  (loads .env before os.getenv is used)

log = logging.getLogger(__name__)

BASE_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "cerebras": "https://api.cerebras.ai/v1",
    "mistral": "https://api.mistral.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
}


DEFAULT_CHAIN = "groq,cerebras,mistral,openrouter,gemini"


class AllProvidersFailed(RuntimeError):
    """Every configured provider was rate-limited, down or unreachable."""


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    api_key: str
    model: str
    extra: dict = field(default_factory=dict)   # provider-specific request fields, sent via extra_body

    def client(self) -> OpenAI:
        return OpenAI(api_key=self.api_key, base_url=self.base_url,
                      timeout=float(os.getenv("ADVISOR_TIMEOUT_S", "60")), max_retries=0)


def _effort_extra(model: str) -> dict:
    # medium, not low: at low effort gpt-oss skipped tool calls on Hindi input (observed 2026-11-08); medium costs ~5% more
    effort = os.getenv("ADVISOR_REASONING_EFFORT", "medium").strip().lower()
    return {"reasoning_effort": effort} if effort and effort != "default" and "gpt-oss" in model else {}


def chain() -> list[Provider]:
    """Configured providers in the order they should be tried. Read at call time so tests and the UI can switch."""
    groq_model = os.getenv("ADVISOR_MODEL_GROQ", "openai/gpt-oss-120b")
    cerebras_model = os.getenv("ADVISOR_MODEL_CEREBRAS", "gpt-oss-120b")
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    openrouter_model = os.getenv("ADVISOR_MODEL_OPENROUTER", "openai/gpt-oss-120b:free")
    cands = {
        "groq": Provider("groq", BASE_URLS["groq"], os.getenv("GROQ_API_KEY", ""), groq_model, _effort_extra(groq_model)),
        "cerebras": Provider("cerebras", BASE_URLS["cerebras"], os.getenv("CEREBRAS_API_KEY", ""), cerebras_model,
                             _effort_extra(cerebras_model)),
        "mistral": Provider("mistral", BASE_URLS["mistral"], os.getenv("MISTRAL_API_KEY", ""),
                            os.getenv("ADVISOR_MODEL_MISTRAL", "mistral-small-latest")),
        "openrouter": Provider("openrouter", BASE_URLS["openrouter"], os.getenv("OPENROUTER_API_KEY", ""), openrouter_model,
                               _effort_extra(openrouter_model)),
        "gemini": Provider("gemini", BASE_URLS["gemini"], os.getenv("GEMINI_API_KEY", ""), gemini_model),
    }
    order = [p.strip().lower() for p in os.getenv("ADVISOR_PROVIDER_CHAIN", DEFAULT_CHAIN).split(",")]
    return [cands[n] for n in order if n in cands and cands[n].api_key]


def _retry_after(e: Exception, default: float) -> float:
    resp = getattr(e, "response", None)
    value = resp.headers.get("retry-after") if resp is not None else None
    try:
        return float(value) if value is not None else default
    except ValueError:
        return default


def _call(p: Provider, kwargs: dict):
    client = p.client()
    try:
        return client.chat.completions.create(model=p.model, extra_body=p.extra or None, **kwargs)
    except BadRequestError:
        if not p.extra:
            raise
        log.info("advisor: %s rejected %s, retrying without it", p.name, list(p.extra))
        return client.chat.completions.create(model=p.model, **kwargs)


def chat_completion(max_wait_s: float | None = None, **kwargs):
    """Call the first provider that answers; return (response, provider_name).

    Transient failures (429, 5xx, timeouts, network) move on to the next provider. Genuine request errors (other 4xx)
    are raised at once so a bad request is never masked by a provider switch. If every provider is unavailable and
    the shortest retry-after fits in max_wait_s, wait and go round once more.
    """
    providers = chain()
    if not providers:
        raise AllProvidersFailed("no advisor provider configured: set GROQ_API_KEY, CEREBRAS_API_KEY or GEMINI_API_KEY")
    if max_wait_s is None:
        max_wait_s = float(os.getenv("ADVISOR_MAX_WAIT_S", "20"))
    deadline = time.monotonic() + max_wait_s
    last: Exception | None = None
    while True:
        waits: list[float] = []
        for p in providers:
            try:
                return _call(p, kwargs), p.name
            except RateLimitError as e:
                last = e
                waits.append(_retry_after(e, 10.0))
                log.warning("advisor: %s rate-limited (retry-after %.0fs): %s", p.name, waits[-1], str(e)[:160])
            except APIConnectionError as e:          # includes timeouts
                last = e
                waits.append(3.0)
                log.warning("advisor: %s unreachable (%s)", p.name, type(e).__name__)
            except APIStatusError as e:
                last = e
                if e.status_code < 500 and e.status_code != 429:
                    raise
                waits.append(3.0)
                log.warning("advisor: %s returned HTTP %s", p.name, e.status_code)
        wait = min(waits) if waits else None
        if wait is None or time.monotonic() + wait > deadline:
            raise AllProvidersFailed(f"all advisor providers failed: {last}") from last
        log.info("advisor: all providers busy, waiting %.0fs", wait)
        time.sleep(wait + 0.5)
