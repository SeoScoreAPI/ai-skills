"""Tests for ada_report.py (no network): WCAG mapping, compare, unbranded + branded PDFs.

    pip install fpdf2 pypdf pytest && pytest skills/ada-report/tests
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("ada_report", HERE.parent / "scripts" / "ada_report.py")
ar = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
sys.modules["ada_report"] = ar
spec.loader.exec_module(ar)  # type: ignore[union-attr]

RESULT = {
    "url": "https://client-example.com/", "score": 72.5, "grade": "C",
    "standard": "WCAG 2.1 AA", "response_code": 200,
    "summary": {"total_rules_checked": 49, "violations": 2, "passes": 30, "incomplete": 1},
    "lawsuit_risk": {"level": "medium", "summary": "Some lawsuit-risk wording."},
    "violations": [
        {"rule_id": "color-contrast", "impact": "serious", "help": "Contrast too low",
         "wcag_tags": ["wcag2aa", "wcag143"], "affected_elements": 5, "fix": "Darken text",
         "element_samples": [{"target": [".a"], "html": "<span>x</span>"},
                             {"target": [".b"], "html": "<span>y</span>"}]},
        {"rule_id": "image-alt", "impact": "critical", "help": "Images need alt text",
         "wcag_tags": ["wcag2a", "wcag111"], "affected_elements": 1, "element_samples": []},
    ],
    "best_practices": [{"rule_id": "heading-order", "help": "Heading order", "affected_elements": 1}],
    "needs_review": [{"rule_id": "video-caption", "help": "Check captions", "affected_elements": 1}],
}


def audit(result: dict, when: str = "2026-09-29T21:50:00+00:00") -> dict:
    d = ar.wrap("https://client-example.com", result)
    d["audited_at"] = when
    return d


def text_of(pdf: Path) -> str:
    pypdf = pytest.importorskip("pypdf")
    return " ".join(p.extract_text() for p in pypdf.PdfReader(str(pdf)).pages)


def test_wcag_tags_map_to_success_criteria() -> None:
    assert ar.criteria(["wcag2aa", "wcag143", "wcag1410", "cat.color"]) == ["1.4.3", "1.4.10"]
    assert ar.sc_label("1.4.3") == "1.4.3 Contrast (Minimum) (AA)"
    assert ar.sc_label("9.9.9") == "9.9.9"


def test_violations_sorted_by_impact() -> None:
    assert [v["rule_id"] for v in ar.violations(RESULT)] == ["image-alt", "color-contrast"]


def test_fingerprint_is_stable_and_detects_edits(tmp_path: Path) -> None:
    d = audit(RESULT)
    assert d["sha256"] == ar.fingerprint(copy.deepcopy(RESULT))
    f = tmp_path / "a.json"
    d["result"]["score"] = 99
    f.write_text(json.dumps(d))
    assert ar.fingerprint(ar.load(f)["result"]) != d["sha256"]


def test_compare_resolved_open_new() -> None:
    after = copy.deepcopy(RESULT)
    after["violations"] = [dict(RESULT["violations"][0], affected_elements=2,
                                element_samples=RESULT["violations"][0]["element_samples"][:1]),
                           {"rule_id": "label", "impact": "critical", "help": "Form labels",
                            "wcag_tags": ["wcag2a", "wcag412"], "affected_elements": 3}]
    d = ar.diff(audit(RESULT), audit(after, "2026-10-06T15:00:00+00:00"))
    assert [v["rule_id"] for v in d["resolved"]] == ["image-alt"]
    assert [v["rule_id"] for v in d["new"]] == ["label"]
    (still,) = d["still_open"]
    assert still["_before"] == 5 and still["affected_elements"] == 2
    assert still["_fixed_samples"] == [".b"]


def test_default_pdf_is_unbranded(tmp_path: Path) -> None:
    out = ar.render_audit(audit(RESULT), tmp_path / "r.pdf")
    t = text_of(out).lower()
    for vendor in ("seo score", "seoscore", "score api"):
        assert vendor not in t
    assert "lawsuit" not in t  # risk flag is opt-in
    assert "1.4.3 contrast (minimum) (aa)" in t and "reviewed by" in t and "signature" in t
    pypdf = pytest.importorskip("pypdf")
    meta = pypdf.PdfReader(str(out)).metadata or {}
    assert not any("seo" in str(v).lower() for v in meta.values())


def test_branded_pdf_carries_the_firm(tmp_path: Path) -> None:
    pil = pytest.importorskip("PIL.Image")
    logo = tmp_path / "logo.png"
    pil.new("RGB", (200, 60), "navy").save(logo)
    brand = ar.Branding(firm="Sample & Partners LLP", logo=logo,
                        prepared_for="Acme Corp. / Matter 2026-114", prepared_by="Jane Doe",
                        include_risk=True)
    t = text_of(ar.render_audit(audit(RESULT), tmp_path / "b.pdf", brand))
    assert t.count("Sample & Partners LLP") >= 2  # header + footer
    assert "Acme Corp. / Matter 2026-114" in t and "Jane Doe" in t
    assert "lawsuit-risk wording" in t


def test_signature_block_can_be_turned_off(tmp_path: Path) -> None:
    t = text_of(ar.render_audit(audit(RESULT), tmp_path / "n.pdf",
                                ar.Branding(signature_block=False)))
    assert "Reviewed by" not in t


def test_compare_pdf_renders_branded(tmp_path: Path) -> None:
    after = copy.deepcopy(RESULT)
    after["violations"] = after["violations"][:1]
    t = text_of(ar.render_compare(audit(RESULT), audit(after), tmp_path / "c.pdf",
                                  ar.Branding(firm="Sample & Partners LLP")))
    assert "Accessibility Remediation Report" in t and "Sample & Partners LLP" in t
    assert "seoscore" not in t.lower()


def test_missing_logo_is_a_clear_error(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="image not found"):
        ar.render_audit(audit(RESULT), tmp_path / "x.pdf",
                        ar.Branding(logo=tmp_path / "nope.png"))


def test_errors_are_plain_english() -> None:
    assert "blocks automated browsers" in ar.explain(422, "refused (HTTP 403)")
    assert "pricing" in ar.explain(403, "limit")
    assert "API key" in ar.explain(401, "")


def test_guessable_flag_aliases_work(tmp_path: Path) -> None:
    f = tmp_path / "a.json"
    f.write_text(json.dumps(audit(RESULT)))
    ar.main(["pdf", str(f), "--out", str(tmp_path / "a.pdf"), "--firm-name", "X LLP",
             "--reviewer", "Jane Doe"])
    t = text_of(tmp_path / "a.pdf")
    assert "X LLP" in t and "Jane Doe" in t


TRACKERS = {
    "method": "browser",
    "summary": {"trackers": 2, "tracker_requests": 5, "page_requests": 40, "consent_manager": None},
    "trackers": [
        {"id": "ga4", "vendor": "Google Analytics", "category": "analytics",
         "found_in": ["html", "network"], "injected": False, "requests": 2,
         "evidence": ["https://www.google-analytics.com/g/collect"], "ids": ["G-TEST123"]},
        {"id": "meta_pixel", "vendor": "Meta Pixel", "category": "advertising",
         "found_in": ["network"], "injected": True, "requests": 3,
         "evidence": ["https://connect.facebook.net/en_US/fbevents.js"]},
    ],
    "consent_managers": [],
    "notes": [],
}


def test_no_tracker_section_unless_the_audit_asked(tmp_path: Path) -> None:
    txt = text_of(ar.render_audit(audit(RESULT), tmp_path / "a.pdf"))
    assert "trackers" not in txt.lower()


def test_tracker_inventory_section(tmp_path: Path) -> None:
    txt = text_of(ar.render_audit(audit({**RESULT, "trackers": TRACKERS}), tmp_path / "a.pdf"))
    txt = " ".join(txt.split())  # the PDF wraps lines
    assert "Third-party trackers loaded by this page" in txt
    for needle in ("Google Analytics", "G-TEST123", "Meta Pixel", "Advertising",
                   "added by a tag manager", "google-analytics.com/g/collect",
                   "none detected", "5 of 40"):
        assert needle in txt, needle
    # An inventory, never a finding about consent or liability.
    assert "It does not say" in txt and "not legal advice" in txt
    for word in ("violation of", "illegal", "unlawful", "exposure", "liable"):
        assert word not in txt.lower(), word


def test_tracker_block_changes_the_fingerprint() -> None:
    assert ar.fingerprint(RESULT) != ar.fingerprint({**RESULT, "trackers": TRACKERS})


def test_tracker_inventory_empty_and_failed(tmp_path: Path) -> None:
    empty = {**TRACKERS, "trackers": [], "consent_managers": [{"vendor": "OneTrust"}]}
    txt = text_of(ar.render_audit(audit({**RESULT, "trackers": empty}), tmp_path / "e.pdf"))
    assert "No known analytics" in txt and "OneTrust" in txt
    failed = {"error": "The tracker inventory could not be collected for this page."}
    txt = text_of(ar.render_audit(audit({**RESULT, "trackers": failed}), tmp_path / "f.pdf"))
    assert "could not be collected" in txt


def test_trackers_flag_asks_the_api_for_them(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps(RESULT).encode()

    monkeypatch.setenv("SEO_SCORE_API_KEY", "k")
    monkeypatch.setattr(ar.urllib.request, "urlopen", lambda req, timeout=0: seen.append(req.full_url) or Resp())
    ar.run_audit("https://client-example.com")
    ar.run_audit("https://client-example.com", trackers=True)
    assert "include=" not in seen[0] and seen[1].endswith("include=trackers")
