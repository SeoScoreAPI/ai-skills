"""Tests for --local (no network, no browser): scoring parity, provenance, privacy, CLI.

    pip install fpdf2 pypdf pytest && pytest skills/ada-report/tests
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"


def _load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


ar = _load("ada_report")
la = _load("local_audit")

WCAG = ["wcag2aa", "wcag143"]


def node(target: str, contrast: str | None = None) -> dict[str, Any]:
    n: dict[str, Any] = {"html": f"<p class='{target}'>x</p>", "target": [f".{target}"],
                         "failureSummary": "Fix any of the following"}
    if contrast:
        n["any"] = [{"data": {"contrastRatio": contrast, "fgColor": "#777777",
                              "bgColor": "#0a0a0a", "expectedContrastRatio": "4.5:1"},
                     "message": "low contrast"}]
    return n


AXE = {
    "violations": [
        {"id": "color-contrast", "impact": "serious", "tags": WCAG, "help": "Contrast",
         "helpUrl": "https://example.test/cc", "nodes": [node("a", "4.42")]},
        {"id": "landmark-unique", "impact": "moderate", "tags": ["best-practice"],
         "help": "Landmarks unique", "nodes": [node("b")]},
    ],
    "passes": [{"id": f"pass-{i}", "tags": ["wcag2a"], "nodes": []} for i in range(32)]
    + [{"id": "bp-pass", "tags": ["best-practice"], "nodes": []}] * 21,
    "incomplete": [{"id": "color-contrast", "impact": "serious", "tags": WCAG,
                    "help": "Contrast", "nodes": [node("c")]}],
}


def local_result(label: str = "Office laptop") -> dict[str, Any]:
    r = la.build_report(AXE, "https://client-example.com/", 200)
    r["run"] = {"location": "local", "tool_version": ar.VERSION,
                "machine": la.machine_info(label),
                "network": {"ip_version": 4,
                            "local_address_class": la.address_class("192.168.1.20")},
                "browser": {"engine": "Chromium (Playwright)", "version": "159.0",
                            "headless": True, "user_agent": "Mozilla/5.0 HeadlessChrome/159.0"},
                "axe_core": {"version": la.AXE_VERSION, "source": la.AXE_URL, "sha256": "ab" * 32}}
    return r


def text_of(pdf: Path) -> str:
    pypdf = pytest.importorskip("pypdf")
    return " ".join(" ".join(p.extract_text() for p in pypdf.PdfReader(str(pdf)).pages).split())


def test_scoring_matches_the_hosted_formula() -> None:
    r = la.build_report(AXE, "https://client-example.com/", 200)
    # 32 WCAG passes, 1 serious WCAG failure on 1 element: 32/33*100 - (5 + 1) = 90.97 -> 91.0
    assert r["score"] == 91.0 and r["grade"] == "A"
    assert r["summary"] == {"total_rules_checked": 56, "violations": 1, "passes": 32,
                            "incomplete": 1, "best_practice_issues": 1}
    (v,) = r["violations"]
    assert v["type"] == "wcag" and v["wcag_tags"] == WCAG
    assert "4.42:1 (#777777 on #0a0a0a)" in v["element_samples"][0]["fix_suggestion"]
    assert [b["rule_id"] for b in r["best_practices"]] == ["landmark-unique"]
    assert r["needs_review"][0]["what_to_check"]
    assert [p["severity"] for p in r["priorities"]] == ["high", "low"]


def test_no_decided_rules_scores_100() -> None:
    assert la.build_report({}, "u", 200)["score"] == 100.0
    assert [la.grade_for(s) for s in (95, 90, 80, 70, 60, 59.9)] == ["A+", "A", "B", "C", "D", "F"]


def test_network_is_a_class_never_an_address() -> None:
    assert "private" in la.address_class("10.0.0.5")
    assert "carrier-grade" in la.address_class("100.72.1.1")
    assert "public" in la.address_class("8.8.8.8")
    assert "loopback" in la.address_class("127.0.0.1")
    assert la.address_class("not-an-ip") == "unknown"


def test_network_class_drops_the_address(monkeypatch: pytest.MonkeyPatch) -> None:
    class Sock:
        def __init__(self, *a: Any) -> None: ...
        def __enter__(self) -> Sock: return self  # noqa: PYI034
        def __exit__(self, *a: object) -> None: ...
        def connect(self, addr: Any) -> None: ...
        def getsockname(self) -> tuple[str, int]: return ("192.168.7.33", 5555)

    monkeypatch.setattr(la.socket, "getaddrinfo",
                        lambda *a, **k: [(2, 2, 17, "", ("93.184.216.34", 443))])
    monkeypatch.setattr(la.socket, "socket", Sock)
    net = la.network_class("client-example.com")
    assert net["ip_version"] == 4 and "private" in net["local_address_class"]
    assert "192.168" not in json.dumps(net) and "93.184" not in json.dumps(net)


def test_bot_checks_and_refusals_stop_the_run() -> None:
    for status in (401, 403, 429, 503):
        assert "does not try to get past bot protection" in la.status_problem(status)
    assert la.status_problem(200) is None and "not found" in la.status_problem(404)
    for title in ("Just a moment...", "Attention Required! | Cloudflare", "Access Denied"):
        assert "does not solve or get around" in la.challenge_problem(title)
    assert la.challenge_problem("Acme Plumbing | Home") is None


def test_local_pdf_is_marked_and_still_unbranded(tmp_path: Path) -> None:
    data = ar.wrap("https://client-example.com", local_result())
    assert data["api"] == "local browser run" and ar.is_local(data["result"])
    t = text_of(ar.render_audit(data, tmp_path / "l.pdf"))
    for needle in ("Website Accessibility Audit (local run)", "LOCAL RUN", "Office laptop",
                   "private address behind a router", "address not recorded",
                   "identity unchanged", "axe-core 4.10.3", "No IP address, host name or user name"):
        assert needle in t, needle
    assert "seoscore" not in t.lower() and "seo score" not in t.lower()


def test_hosted_pdf_has_no_local_markings(tmp_path: Path) -> None:
    hosted = la.build_report(AXE, "https://client-example.com/", 200)
    t = text_of(ar.render_audit(ar.wrap("https://client-example.com", hosted), tmp_path / "h.pdf"))
    assert "local run" not in t.lower() and "LOCAL RUN" not in t


def test_fingerprint_covers_the_run_block() -> None:
    a, b = local_result("Office laptop"), local_result("Other laptop")
    assert ar.fingerprint(a) != ar.fingerprint(b)
    hosted = dict(a)
    hosted.pop("run")
    assert ar.fingerprint(hosted) != ar.fingerprint(a)  # stripping "local" breaks the hash


def test_compare_notes_mixed_runs(tmp_path: Path) -> None:
    hosted = la.build_report(AXE, "https://client-example.com/", 200)
    t = text_of(ar.render_compare(ar.wrap("https://client-example.com", hosted),
                                  ar.wrap("https://client-example.com", local_result()),
                                  tmp_path / "c.pdf"))
    assert "local run" in t and "One audit was a local run" in t


def test_cli_local_needs_no_key_and_marks_files(tmp_path: Path,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEO_SCORE_API_KEY", raising=False)
    seen: dict[str, Any] = {}

    def fake(url: str, **kw: Any) -> dict[str, Any]:
        seen.update(url=url, **kw)
        return local_result(kw.get("machine_label", ""))

    monkeypatch.setattr(la, "run_local", fake)
    monkeypatch.setattr(ar.urllib.request, "urlopen",
                        lambda *a, **k: pytest.fail("the hosted API must not be called"))
    ar.main(["audit", "https://client-example.com", "--local", "--machine-label", "Desk 4",
             "--out", str(tmp_path)])
    assert seen["machine_label"] == "Desk 4" and seen["headed"] is False
    (js,) = tmp_path.glob("*-local.json")
    assert (tmp_path / js.name.replace(".json", ".pdf")).is_file()
    saved = json.loads(js.read_text())
    assert saved["result"]["run"]["machine"]["label"] == "Desk 4"
    assert ar.fingerprint(ar.load(js)["result"]) == saved["sha256"]


def test_cli_local_failure_is_a_plain_message(tmp_path: Path,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(url: str, **kw: Any) -> dict[str, Any]:
        raise la.LocalAuditError(la.status_problem(403))

    monkeypatch.setattr(la, "run_local", refuse)
    with pytest.raises(SystemExit, match="refused this computer too"):
        ar.main(["audit", "https://client-example.com", "--local", "--out", str(tmp_path)])
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("argv", [["--local", "--trackers"], ["--machine-label", "x"], ["--headed"]])
def test_cli_rejects_flag_mixups(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        ar.main(["audit", "https://client-example.com", *argv])


def test_blocked_error_points_to_local() -> None:
    assert "--local" in ar.explain(422, "refused (HTTP 403)")
