"""Deep Site Audit commands of seo_audit.py. No network: _engine_request is patched."""

import importlib
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load(monkeypatch, **env):
    for k in ("SEO_SCORE_DEEP_AUDIT_URL", "SEO_SCORE_ENGINE_URL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SEO_SCORE_API_KEY", "k")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import seo_audit
    mod = importlib.reload(seo_audit)
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    return mod


class Recorder:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, path, headers=None, body=None):
        self.calls.append((method, path, body))
        return self.responses.pop(0)


def test_defaults_to_main_host(monkeypatch):
    m = load(monkeypatch)
    assert m.DEEP_AUDIT_URL == "https://seoscoreapi.com"
    assert m._deep_usage_path() == "/deep-audit/usage"


def test_env_overrides(monkeypatch):
    assert load(monkeypatch, SEO_SCORE_ENGINE_URL="https://engine.seoscoreapi.com").DEEP_AUDIT_URL == "https://engine.seoscoreapi.com"
    m = load(monkeypatch, SEO_SCORE_DEEP_AUDIT_URL="http://localhost:9000/", SEO_SCORE_ENGINE_URL="https://engine.seoscoreapi.com")
    assert m.DEEP_AUDIT_URL == "http://localhost:9000"
    assert load(monkeypatch, SEO_SCORE_DEEP_AUDIT_URL="https://engine.seoscoreapi.com")._deep_usage_path() == "/usage"


def test_engine_request_builds_main_host_url(monkeypatch):
    m = load(monkeypatch)
    seen = {}

    class Resp:
        status = 200
        def read(self):
            return b'{"ok": 1}'
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        return Resp()

    monkeypatch.setattr(m.urllib.request, "urlopen", fake_urlopen)
    assert m._engine_request("GET", "/site-audit/abc") == (200, {"ok": 1})
    assert seen["url"] == "https://seoscoreapi.com/site-audit/abc"


def test_deep_polls_to_completion(monkeypatch, capsys):
    m = load(monkeypatch)
    rec = Recorder([
        (200, {"job_id": "abc", "status": "queued"}),
        (200, {"status": "queued", "queue_position": 1, "eta_seconds": 30}),
        (200, {"status": "completed", "result": {"scores": {}}}),
    ])
    monkeypatch.setattr(m, "_engine_request", rec)
    monkeypatch.setattr(m, "_print_deep", lambda r: print("RESULT", r))
    m.cmd_deep("example.com", business_type="saas")
    assert rec.calls[0] == ("POST", "/site-audit", {"url": "https://example.com", "business_type": "saas"})
    assert rec.calls[2][1] == "/site-audit/abc"
    assert "RESULT" in capsys.readouterr().out


def test_deep_start_and_status(monkeypatch, capsys):
    m = load(monkeypatch)
    rec = Recorder([(200, {"job_id": "abc", "status": "queued"}), (200, {"status": "running", "progress": 40, "stage": "Section 4"})])
    monkeypatch.setattr(m, "_engine_request", rec)
    m.cmd_deep_start("https://example.com")
    m.cmd_deep_status("abc")
    out = capsys.readouterr().out
    assert "job abc" in out and "40%" in out
    assert rec.calls[1][1] == "/site-audit/abc"


def test_deep_usage(monkeypatch, capsys):
    m = load(monkeypatch)
    rec = Recorder([(200, {"tier": "pro", "site_audit": {"used": 3, "remaining": 17}})])
    monkeypatch.setattr(m, "_engine_request", rec)
    m.cmd_deep_usage()
    assert rec.calls[0][1] == "/deep-audit/usage"
    assert "3 used, 17 remaining" in capsys.readouterr().out


def test_no_credits_is_explained(monkeypatch, capsys):
    m = load(monkeypatch)
    monkeypatch.setattr(m, "_engine_request", Recorder([(402, {"detail": "No Deep Audit credits left."})]))
    with pytest.raises(SystemExit):
        m.cmd_deep_start("https://example.com")
    assert "No Deep Audits left" in capsys.readouterr().err


def test_failed_job_exits(monkeypatch):
    m = load(monkeypatch)
    monkeypatch.setattr(m, "_engine_request", Recorder([(200, {"job_id": "abc"}), (200, {"status": "failed", "error": "boom"})]))
    with pytest.raises(SystemExit):
        m.cmd_deep("https://example.com")
