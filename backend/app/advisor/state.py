"""Per-conversation advisor state. Serialisable so the API can keep it in SQLite between turns."""
from ..engine.models import Bundle, Profile
from .prompts import system_prompt


class State:
    def __init__(self, language: str = "en"):
        self.messages: list[dict] = [{"role": "system", "content": system_prompt(language)}]
        self.profile = Profile(language=language)
        self.recommendation: Bundle | None = None
        self.language = language                  # en | hi | hinglish
        self.provider: str | None = None          # which provider answered the last turn (or "cache" / "offline")
        self.needs_known = False                  # owner was asked what to solve (or said "just internet")
        self.unsure_turns = 0                     # "I don't know" answers seen by the offline path
        self.pending: str | None = None           # field the deterministic fallback last asked about
        self.ready_turns = 0                    # owner turns that ended with all five facts known but no quote yet
        self.allowed_numbers: set[int] = set()    # every figure the engine has handed the model (guard whitelist)
        self.allowed_names: set[str] = set()      # product names the engine offered (e.g. in an add-a-line alternative)
        self.line_for_addons = False              # owner agreed to an Accel line for add-ons on a services-only ask
        self.quantities: dict[str, int] = {}      # owner-confirmed quantity overrides, e.g. {"P23": 50}
        self.assumed: dict = {}                   # defaults used when the owner could not answer
        self.user_turns: list[str] = []
        self.usage = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}
        self.warnings: list[str] = []             # guard findings (stray product names / prices), for the runner

    # -- persistence -------------------------------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "messages": self.messages[1:],                       # system prompt is re-attached on load
            "profile": self.profile.model_dump(mode="json"),
            "recommendation": self.recommendation.model_dump(mode="json") if self.recommendation else None,
            "language": self.language,
            "provider": self.provider,
            "needs_known": self.needs_known,
            "ready_turns": self.ready_turns,
            "pending": self.pending,
            "unsure_turns": self.unsure_turns,
            "allowed_numbers": sorted(self.allowed_numbers),
            "allowed_names": sorted(self.allowed_names),
            "line_for_addons": self.line_for_addons,
            "quantities": self.quantities,
            "assumed": self.assumed,
            "user_turns": self.user_turns,
            "usage": self.usage,
            "warnings": self.warnings,
        }

    def set_language(self, language: str) -> None:
        """Language changes rewrite the system prompt's last line so the model is told explicitly which to use."""
        self.language = language
        self.messages[0] = {"role": "system", "content": system_prompt(language)}
        self.profile = self.profile.model_copy(update={"language": language})

    def load(self, d: dict) -> "State":
        self.messages = [{"role": "system", "content": system_prompt(d.get("language", "en"))}] + list(d.get("messages", []))
        self.profile = Profile(**d.get("profile", {}))
        self.recommendation = Bundle(**d["recommendation"]) if d.get("recommendation") else None
        self.language = d.get("language", "en")
        self.provider = d.get("provider")
        self.needs_known = bool(d.get("needs_known", False))
        self.ready_turns = int(d.get("ready_turns", 0))
        self.pending = d.get("pending")
        self.unsure_turns = int(d.get("unsure_turns", 0))
        self.allowed_numbers = set(d.get("allowed_numbers", []))
        self.allowed_names = set(d.get("allowed_names", []))
        self.line_for_addons = bool(d.get("line_for_addons", False))
        self.quantities = dict(d.get("quantities", {}))
        self.assumed = dict(d.get("assumed", {}))
        self.user_turns = list(d.get("user_turns", []))
        self.usage = dict(d.get("usage", {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}))
        self.warnings = list(d.get("warnings", []))
        return self

    @classmethod
    def from_dict(cls, d: dict) -> "State":
        return cls(language=d.get("language", "en")).load(d)
