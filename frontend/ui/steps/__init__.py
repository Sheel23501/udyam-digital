from . import chat, consent, done, kyc, language, otp, quote, tracker  # noqa: F401

STEPS = {"language": language, "otp": otp, "chat": chat, "quote": quote, "consent": consent, "kyc": kyc, "tracker": tracker, "done": done}
