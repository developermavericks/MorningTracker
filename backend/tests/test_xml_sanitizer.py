import os
import tempfile
import pytest
from scraper.report_generator import (
    sanitize_for_xml,
    generate_docx_report,
    generate_organized_docx_report,
    generate_excel_report,
    generate_mailer_docx_report
)

def test_sanitize_for_xml_unit():
    assert sanitize_for_xml(None) == ""
    assert sanitize_for_xml(12345) == "12345"
    assert sanitize_for_xml("Normal text") == "Normal text"
    # Preserves valid whitespace (\n, \r, \t)
    assert sanitize_for_xml("Line 1\nLine 2\r\tTabbed") == "Line 1\nLine 2\r\tTabbed"
    # Strips null bytes and control chars
    corrupted = "Header\x00Body\x0bText\x0cFooter\x1f"
    assert sanitize_for_xml(corrupted) == "HeaderBodyTextFooter"

def test_report_generation_with_corrupted_xml_strings():
    with tempfile.TemporaryDirectory() as tmpdir:
        corrupted_summary = "Article summary containing NULL byte \x00 and vertical tab \x0b and form feed \x0c!"
        corrupted_title = "Corrupted Title \x00 With Control \x1f Chars"
        
        grouped_data = {
            "Master Category \x00": {
                "Sub Category \x0b": [
                    {
                        "title": corrupted_title,
                        "url": "https://example.com/article\x001",
                        "agency": "Corrupted Press \x00",
                        "author": "John Doe \x0c",
                        "summary": corrupted_summary,
                        "full_body": corrupted_summary,
                        "published_at": "2026-09-02",
                        "confidence_score": 9
                    }
                ]
            }
        }
        
        # 1. Test generate_mailer_docx_report (which crashed previously for Boston Scientific)
        mailer_docx_path = os.path.join(tmpdir, "test_mailer.docx")
        out1 = generate_mailer_docx_report(
            client_name="Boston Scientific \x00",
            report_type="Daily Brief Mailer",
            date_str="2026-09-02",
            exec_summary=f"- Bullet 1 with \x00 null byte\n- Bullet 2 with \x0b control char",
            takeaways=f"**Takeaway 1 \x00** — Implication \x0c",
            grouped_data=grouped_data,
            output_path=mailer_docx_path
        )
        assert os.path.exists(out1)
        assert os.path.getsize(out1) > 0

        # 2. Test generate_organized_docx_report
        org_docx_path = os.path.join(tmpdir, "test_organized.docx")
        out2 = generate_organized_docx_report(
            client_name="Boston Scientific",
            report_type="Master Intelligence Report",
            date_str="2026-09-02",
            grouped_data=grouped_data,
            output_path=org_docx_path
        )
        assert os.path.exists(out2)
        assert os.path.getsize(out2) > 0

        # 3. Test generate_excel_report
        excel_path = os.path.join(tmpdir, "test_report.xlsx")
        out3 = generate_excel_report(
            client_name="Boston Scientific",
            report_type="Master Excel Report",
            date_str="2026-09-02",
            grouped_data=grouped_data,
            output_path=excel_path
        )
        assert os.path.exists(out3)
        assert os.path.getsize(out3) > 0

        # 4. Test generate_docx_report
        plain_docx_path = os.path.join(tmpdir, "test_plain.docx")
        data_plain = {
            "Section 1": [
                {
                    "title": corrupted_title,
                    "agency": "Test Agency \x00",
                    "summary": corrupted_summary,
                    "url": "https://example.com/art2\x00"
                }
            ]
        }
        out4 = generate_docx_report(
            client_name="Boston Scientific",
            date_str="2026-09-02",
            data=data_plain,
            output_path=plain_docx_path
        )
        assert os.path.exists(out4)
        assert os.path.getsize(out4) > 0
