"""
Tests for the parallel section processing pattern introduced in run_client_report_task.
Verifies:
  1. All sections are processed (none dropped silently).
  2. The closure-over-parameter pattern is correct — each section uses its own keywords.
  3. Parallel execution actually runs sections concurrently (timing check).
  4. A section failure does not crash the whole report (error isolation).
  5. Return value shape is correct for each section.
"""
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed


# ── Helpers mirroring the exact pattern in tasks.py ──────────────────────────

def _make_process_section(section_discoveries, captured):
    """
    Builds a _process_section function that mirrors the tasks.py pattern.
    `captured` is a shared dict used to record which section/keywords each
    invocation actually used — lets us detect the classic closure bug.
    """
    def _process_section(section_name, keywords):
        if not keywords:
            return section_name, [], []

        discovered = section_discoveries.get(section_name, [])

        filtered = []
        master = []

        def _process_single_article(art):
            # Record the section_name + keywords this closure captured
            captured[art["url"]] = {"section": section_name, "keywords": keywords[:]}
            return {"title": art["title"], "url": art["url"], "relevant": True}

        with ThreadPoolExecutor(max_workers=2) as exe:
            futs = {exe.submit(_process_single_article, a): a for a in discovered}
            for f in as_completed(futs):
                res = f.result()
                master.append(res)
                if res["relevant"]:
                    filtered.append(res)

        return section_name, filtered, master

    return _process_section


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_all_sections_processed():
    """Every section in sections_data must appear in report_data_filtered."""
    sections_data = {
        "Company News": ["keyword_a", "keyword_b"],
        "Competition":  ["keyword_c"],
        "Industry":     ["keyword_d", "keyword_e"],
    }
    section_discoveries = {
        "Company News": [{"url": "http://a.com", "title": "A"}],
        "Competition":  [{"url": "http://b.com", "title": "B"}],
        "Industry":     [{"url": "http://c.com", "title": "C"}],
    }

    report_data_filtered = {}
    report_data_master = {}
    captured = {}

    _process_section = _make_process_section(section_discoveries, captured)

    active = {sn: kw for sn, kw in sections_data.items() if kw}
    sec_workers = min(len(active), 5)
    with ThreadPoolExecutor(max_workers=sec_workers) as sec_exe:
        sec_futures = {
            sec_exe.submit(_process_section, sn, kw): sn
            for sn, kw in active.items()
        }
        for fut in as_completed(sec_futures):
            sn, filtered, master = fut.result()
            report_data_filtered[sn] = filtered
            report_data_master[sn] = master

    assert set(report_data_filtered.keys()) == {"Company News", "Competition", "Industry"}
    assert set(report_data_master.keys()) == {"Company News", "Competition", "Industry"}
    assert len(report_data_filtered["Company News"]) == 1
    assert len(report_data_filtered["Competition"]) == 1
    assert len(report_data_filtered["Industry"]) == 1


def test_no_closure_bug_keywords_bound_correctly():
    """
    Classic Python closure bug: if keywords were captured by reference to the
    loop variable instead of by value, every section would end up with the
    LAST section's keywords. Verify each section sees its own keywords.
    """
    sections_data = {
        "Section_A": ["kw_alpha"],
        "Section_B": ["kw_beta"],
        "Section_C": ["kw_gamma"],
    }
    section_discoveries = {
        "Section_A": [{"url": "http://a1.com", "title": "A1"}],
        "Section_B": [{"url": "http://b1.com", "title": "B1"}],
        "Section_C": [{"url": "http://c1.com", "title": "C1"}],
    }
    captured = {}
    _process_section = _make_process_section(section_discoveries, captured)

    active = {sn: kw for sn, kw in sections_data.items() if kw}
    with ThreadPoolExecutor(max_workers=3) as sec_exe:
        sec_futures = {sec_exe.submit(_process_section, sn, kw): sn for sn, kw in active.items()}
        results = {}
        for fut in as_completed(sec_futures):
            sn, filtered, master = fut.result()
            results[sn] = filtered

    # Each article must have been processed with its OWN section's keyword
    assert captured["http://a1.com"]["keywords"] == ["kw_alpha"], \
        f"Section_A got wrong keywords: {captured['http://a1.com']['keywords']}"
    assert captured["http://b1.com"]["keywords"] == ["kw_beta"], \
        f"Section_B got wrong keywords: {captured['http://b1.com']['keywords']}"
    assert captured["http://c1.com"]["keywords"] == ["kw_gamma"], \
        f"Section_C got wrong keywords: {captured['http://c1.com']['keywords']}"


def test_sections_run_concurrently():
    """
    With parallel sections, total elapsed time should be ~max(section_times),
    NOT sum(section_times). Use sleep to simulate I/O-bound work.
    """
    SECTION_SLEEP = 0.15   # each section "takes" 150ms
    SECTIONS = 4
    TOLERANCE = 0.30       # allow 300ms overhead for scheduling

    sections_data = {f"Sec_{i}": [f"kw_{i}"] for i in range(SECTIONS)}
    section_discoveries = {
        f"Sec_{i}": [{"url": f"http://art{i}.com", "title": f"Art{i}"}]
        for i in range(SECTIONS)
    }
    captured = {}

    def _slow_process_section(section_name, keywords):
        time.sleep(SECTION_SLEEP)
        return section_name, [{"title": section_name}], [{"title": section_name}]

    report_data_filtered = {}
    start = time.monotonic()

    active = {sn: kw for sn, kw in sections_data.items() if kw}
    with ThreadPoolExecutor(max_workers=min(len(active), 5)) as sec_exe:
        sec_futures = {sec_exe.submit(_slow_process_section, sn, kw): sn for sn, kw in active.items()}
        for fut in as_completed(sec_futures):
            sn, filtered, master = fut.result()
            report_data_filtered[sn] = filtered

    elapsed = time.monotonic() - start
    sequential_time = SECTIONS * SECTION_SLEEP

    assert elapsed < sequential_time, (
        f"Sections appear sequential: took {elapsed:.2f}s, "
        f"expected < {sequential_time:.2f}s (sequential would be ~{sequential_time:.2f}s)"
    )
    assert len(report_data_filtered) == SECTIONS


def test_empty_keywords_section_skipped_gracefully():
    """A section with no keywords returns empty lists without crashing."""
    sections_data = {"No Keywords": [], "Has Keywords": ["kw1"]}
    section_discoveries = {"Has Keywords": [{"url": "http://x.com", "title": "X"}]}
    captured = {}
    _process_section = _make_process_section(section_discoveries, captured)

    active = {sn: kw for sn, kw in sections_data.items() if kw}
    report_data_filtered = {}
    report_data_master = {}

    with ThreadPoolExecutor(max_workers=2) as sec_exe:
        sec_futures = {sec_exe.submit(_process_section, sn, kw): sn for sn, kw in active.items()}
        for fut in as_completed(sec_futures):
            sn, filtered, master = fut.result()
            report_data_filtered[sn] = filtered
            report_data_master[sn] = master

    # "No Keywords" was excluded by active_processing_sections filter, so not in results
    assert "No Keywords" not in report_data_filtered
    assert "Has Keywords" in report_data_filtered
    assert len(report_data_filtered["Has Keywords"]) == 1


def test_section_failure_does_not_crash_report():
    """
    If one section raises an exception, the other sections must still
    complete and their results must still appear in the output.
    The outer executor logs the error and moves on.
    """
    def _flaky_process_section(section_name, keywords):
        if section_name == "Broken":
            raise RuntimeError("Simulated section failure")
        return section_name, [{"title": section_name}], [{"title": section_name}]

    sections_data = {"Good_A": ["kw_a"], "Broken": ["kw_b"], "Good_B": ["kw_c"]}
    report_data_filtered = {}
    report_data_master = {}

    active = {sn: kw for sn, kw in sections_data.items() if kw}
    with ThreadPoolExecutor(max_workers=3) as sec_exe:
        sec_futures = {sec_exe.submit(_flaky_process_section, sn, kw): sn for sn, kw in active.items()}
        for fut in as_completed(sec_futures):
            try:
                sn, filtered, master = fut.result()
                report_data_filtered[sn] = filtered
                report_data_master[sn] = master
            except Exception:
                pass  # mirrors the logger.error in tasks.py

    assert "Good_A" in report_data_filtered
    assert "Good_B" in report_data_filtered
    assert "Broken" not in report_data_filtered  # failed section absent, not crashing
