"""
Heavy Automation email template builder.

Generates a structured HTML intelligence-brief email matching the
reference layout with sections for Executive Summary, Category Sections,
and Strategic Takeaways.
"""

from datetime import datetime
from typing import Dict, List, Optional


def build_intelligence_brief_html(
    company_name: str,
    date_str: str,
    executive_summary: Optional[str] = None,
    articles_by_pillar: Optional[Dict[str, List[dict]]] = None,
    strategic_takeaways: Optional[str] = None,
) -> str:
    """
    Build HTML for intelligence-brief email with sections:
      - Header
      - Executive Summary
      - Category sections (by pillar)
      - Strategic Takeaways
      - Footer
    """
    articles_by_pillar = articles_by_pillar or {}

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{
            font-family: Calibri, Arial, sans-serif;
            color: #333;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
        }}
        .container {{
            max-width: 800px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .header {{
            border-bottom: 3px solid #0066cc;
            padding-bottom: 15px;
            margin-bottom: 25px;
        }}
        .header h1 {{
            margin: 0 0 5px 0;
            color: #0066cc;
            font-size: 24px;
        }}
        .header .meta {{
            color: #666;
            font-size: 12px;
        }}
        .section {{
            margin-bottom: 30px;
        }}
        .section-title {{
            background: #f0f0f0;
            padding: 10px 15px;
            font-weight: bold;
            font-size: 14px;
            border-left: 4px solid #0066cc;
            margin-bottom: 15px;
        }}
        .executive-summary {{
            background: #e6f2ff;
            padding: 15px;
            border-radius: 4px;
            border-left: 4px solid #0066cc;
            font-style: italic;
            line-height: 1.8;
            margin-bottom: 20px;
        }}
        .article {{
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 1px solid #eee;
        }}
        .article:last-child {{
            border-bottom: none;
        }}
        .article-title {{
            font-weight: bold;
            color: #0066cc;
            margin-bottom: 5px;
            font-size: 13px;
        }}
        .article-title a {{
            color: #0066cc;
            text-decoration: none;
        }}
        .article-meta {{
            font-size: 11px;
            color: #999;
            margin-bottom: 8px;
        }}
        .article-summary {{
            font-size: 13px;
            color: #555;
            line-height: 1.6;
        }}
        .takeaways {{
            background: #fff4e6;
            padding: 15px;
            border-radius: 4px;
            border-left: 4px solid #ff9800;
        }}
        .takeaways ul {{
            margin: 10px 0;
            padding-left: 20px;
        }}
        .takeaways li {{
            margin-bottom: 8px;
            font-size: 13px;
            color: #555;
        }}
        .footer {{
            border-top: 1px solid #eee;
            padding-top: 15px;
            margin-top: 30px;
            font-size: 11px;
            color: #999;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="container">
        {_build_header_html(company_name, date_str)}

        {_build_executive_summary_html(executive_summary) if executive_summary else ""}

        {_build_article_sections_html(articles_by_pillar) if articles_by_pillar else ""}

        {_build_takeaways_html(strategic_takeaways) if strategic_takeaways else ""}

        {_build_footer_html()}
    </div>
</body>
</html>
"""
    return html


def _build_header_html(company_name: str, date_str: str) -> str:
    """Header with company name, title, date."""
    return f"""
<div class="header">
    <h1>{company_name} India</h1>
    <div style="font-size: 16px; font-weight: bold; margin-bottom: 5px;">Daily Intelligence Brief</div>
    <div class="meta">
        <strong>Date:</strong> {date_str}<br>
        <strong>Source:</strong> NEXUS Global News Intelligence
    </div>
</div>
"""


def _build_executive_summary_html(text: str) -> str:
    """Executive summary section."""
    if not text:
        return ""
    return f"""
<div class="section">
    <div class="section-title">📌 Executive Summary</div>
    <div class="executive-summary">{text}</div>
</div>
"""


def _build_article_sections_html(articles_by_pillar: Dict[str, List[dict]]) -> str:
    """Article sections grouped by pillar."""
    if not articles_by_pillar:
        return ""

    html = ""
    for pillar, articles in sorted(articles_by_pillar.items()):
        if not articles:
            continue

        html += f"""
<div class="section">
    <div class="section-title">{pillar}</div>
"""
        for art in articles[:10]:  # Limit to 10 per section in email
            title = art.get("title", "No Title")
            url = art.get("url") or "#"
            summary = art.get("_summary") or art.get("summary") or "No summary available."
            agency = art.get("agency") or "Unknown Publication"
            pub_at = art.get("published_at", "")

            if pub_at:
                try:
                    from datetime import datetime as dt
                    if isinstance(pub_at, str):
                        pub_at = pub_at.split("T")[0]
                    else:
                        pub_at = pub_at.strftime("%Y-%m-%d")
                except:
                    pub_at = str(pub_at)[:10]

            html += f"""
    <div class="article">
        <div class="article-title">
            <a href="{url}" target="_blank">{title}</a>
        </div>
        <div class="article-meta">
            <strong>{agency}</strong> • {pub_at}
        </div>
        <div class="article-summary">{summary}</div>
    </div>
"""
        html += "</div>"

    return html


def _build_takeaways_html(text: str) -> str:
    """Strategic takeaways section."""
    if not text:
        return ""

    # Try to format as bullet list if not already
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    bullets = "\n".join([f"<li>{line}</li>" for line in lines if line])

    return f"""
<div class="section takeaways">
    <div style="font-weight: bold; margin-bottom: 10px;">🎯 Strategic Takeaways</div>
    <ul>{bullets}</ul>
</div>
"""


def _build_footer_html() -> str:
    """Footer with timestamp and disclaimer."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"""
<div class="footer">
    <p>
        Generated by NEXUS Intelligence on {now}.<br>
        This is an automated intelligence briefing. For questions, contact your operations team.
    </p>
</div>
"""
