"""HTTP client for the FastAPI backend, with an in-process fallback.

Modes (API_MODE in .streamlit/secrets.toml or the environment):
  http       - call BACKEND_URL over HTTP (default when the backend answers /health)
  inprocess  - import the backend package and call it through FastAPI's TestClient in this process
               (lets `streamlit run frontend/app.py` work with no second process, e.g. on Streamlit Community Cloud)
  auto       - http if reachable, else inprocess (default)
"""
import os
import sys
from pathlib import Path

import requests
import streamlit as st


class ApiError(Exception):
    def __init__(self, status: int, detail):
        self.status = status
        self.detail = detail
        super().__init__(f"{status}: {detail}")

    def text(self) -> str:
        d = self.detail
        if isinstance(d, dict):
            return str(d.get("message") or d)
        return str(d)


def _setting(name: str, default: str | None = None) -> str | None:
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:  # noqa: BLE001 — no secrets.toml is normal locally
        pass
    return os.getenv(name, default)


BASE = (_setting("BACKEND_URL", "http://localhost:8000") or "").rstrip("/")
MODE_SETTING = (_setting("API_MODE", "auto") or "auto").lower()
TIMEOUT = float(_setting("API_TIMEOUT_S", "90") or 90)


def _export_secrets_to_env() -> None:
    """Streamlit Cloud secrets -> environment, so the in-process backend (which reads os.getenv) sees the API keys.
    Never overrides a variable that is already set."""
    try:
        for k, v in st.secrets.items():
            if isinstance(v, (str, int, float, bool)) and k not in os.environ:
                os.environ[k] = str(v)
    except Exception:  # noqa: BLE001 — no secrets file locally
        pass


@st.cache_resource(show_spinner=False)
def _inprocess_client():
    _export_secrets_to_env()
    root = Path(__file__).resolve().parents[1] / "backend"
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from fastapi.testclient import TestClient  # noqa: PLC0415
    from app.main import app  # noqa: PLC0415

    client = TestClient(app)
    client.__enter__()                      # run the lifespan (builds the SQLite DB) once
    return client


LAST_ERROR: dict = {"inprocess": None, "http": None}


@st.cache_resource(show_spinner=False)
def mode() -> str:
    if MODE_SETTING in ("http", "inprocess"):
        return MODE_SETTING
    try:
        requests.get(BASE + "/health", timeout=2).raise_for_status()
        return "http"
    except Exception as e:  # noqa: BLE001
        LAST_ERROR["http"] = f"{type(e).__name__}: {e}"
        try:
            _inprocess_client()
            return "inprocess"
        except Exception as e2:  # noqa: BLE001
            LAST_ERROR["inprocess"] = f"{type(e2).__name__}: {e2}"
            return "http"


def diagnostics() -> dict:
    """What the page shows under the 'starting up' notice so a broken deploy explains itself."""
    info = {"mode_setting": MODE_SETTING, "mode": mode(), "backend_url": BASE, "python": sys.version.split()[0]}
    if mode() == "inprocess" or MODE_SETTING == "inprocess":
        try:
            _inprocess_client()
            info["inprocess"] = "ok"
        except Exception as e:  # noqa: BLE001
            info["inprocess"] = f"{type(e).__name__}: {e}"
    info.update({k: v for k, v in LAST_ERROR.items() if v})
    return info


def _handle(r):
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", r.text)
        except Exception:  # noqa: BLE001
            detail = r.text
        raise ApiError(r.status_code, detail)
    return r.json() if r.content else None


def _call(method: str, path: str, **kw):
    if mode() == "inprocess":
        try:
            c = _inprocess_client()
        except Exception as e:  # noqa: BLE001 — missing backend package on the host: report, don't crash the page
            LAST_ERROR["inprocess"] = f"{type(e).__name__}: {e}"
            raise ApiError(0, f"in-process backend failed to start: {type(e).__name__}: {e}") from e
        return _handle(getattr(c, method)(path, **kw))
    try:
        return _handle(requests.request(method.upper(), BASE + path, timeout=TIMEOUT, **kw))
    except requests.RequestException as e:
        raise ApiError(0, f"cannot reach the backend at {BASE}: {e.__class__.__name__}") from e


def get(path: str, **params):
    return _call("get", path, params=params or None)


def post(path: str, json=None, data=None, files=None):
    return _call("post", path, json=json, data=data, files=files)


def delete(path: str):
    return _call("delete", path)


def health() -> dict | None:
    try:
        return get("/health")
    except ApiError:
        return None
