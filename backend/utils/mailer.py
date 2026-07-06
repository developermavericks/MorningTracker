from __future__ import annotations

import html
import re
from typing import Any, Mapping, Sequence

# --------------------------------------------------------------------------- #
# Google brand palette
# --------------------------------------------------------------------------- #
BLUE   = "#4285F4"
RED    = "#EA4335"
YELLOW = "#FBBC04"
GREEN  = "#34A853"

_INK       = "#1a1a2e"
_BODY      = "#374151"
_MUTED     = "#6b7280"
_HAIRLINE  = "#e5e7eb"
_LINK      = "#0563c1"
_HEADER_BG = "#1f2937"
_SUBTITLE  = "#9ca3af"
_TAGS      = "#6b7280"

_DOM_FG, _DOM_BG = "#166534", "#dcfce7"     # DOMESTIC pill
_INT_FG, _INT_BG = "#1e40af", "#dbeafe"     # INTERNATIONAL pill

_FONT = "Arial, Helvetica, sans-serif"
_MAX_W = 624                                # 6.5in @ 96dpi, matches template

MAX_SUMMARY_WORDS = 80
_LOGO_PALETTE = [BLUE, RED, YELLOW, BLUE, GREEN, RED]   # cycles across letters


# --------------------------------------------------------------------------- #
# Small helpers                                                                #
# --------------------------------------------------------------------------- #
def esc(s: Any) -> str:
    return html.escape(str(s), quote=True)


def _first(d: Mapping[str, Any], *keys: str) -> str:
    for k in keys:
        v = d.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _pub_list(a: Mapping[str, Any]) -> list[str]:
    v = a.get("publication") or a.get("source") or a.get("agency") or ""
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v if str(x).strip()]
    return [str(v).strip()] if str(v).strip() else []


def _truncate_words(text: str, max_words: int = MAX_SUMMARY_WORDS) -> str:
    words = re.split(r"\s+", text.strip())
    if len(words) <= max_words:
        return text.strip()
    return " ".join(words[:max_words]).rstrip(".,;:") + "…"


def _byline(a: Mapping[str, Any]) -> str:
    """'Publication | Journalist'  or  'Syndicated via Publication'."""
    journalist = _first(a, "journalist", "author", "byline", "reporter")
    pubs = _pub_list(a)
    pub = pubs[0] if pubs else ""
    if journalist:
        return f"{pub} | {journalist}" if pub else journalist
    joined = ", ".join(pubs) if pubs else "wire"
    return f"Syndicated via {joined}"


def _scope(a: Mapping[str, Any]) -> str:
    return (a.get("scope") or "DOMESTIC").strip().upper()


# --------------------------------------------------------------------------- #
# Component renderers                                                          #
# --------------------------------------------------------------------------- #
def _render_logo(brand: str) -> str:
    parts = brand.split(" ", 1)
    first, rest = parts[0], (parts[1] if len(parts) > 1 else "")
    letters = "".join(
        f'<span style="color:{_LOGO_PALETTE[i % len(_LOGO_PALETTE)]}">{esc(ch)}</span>'
        for i, ch in enumerate(first)
    )
    rest_html = f'<span style="color:#ffffff">&nbsp; {esc(rest)}</span>' if rest else ""
    return (
        f'<div style="font-size:26px;font-weight:bold;letter-spacing:.5px;">'
        f"{letters}{rest_html}</div>"
    )


def _render_header(brief: Mapping[str, Any]) -> str:
    brand = brief.get("brand", "Google India")
    subtitle = brief.get("subtitle", "DAILY INTELLIGENCE BRIEF")
    date_str = brief.get("date_str", "")
    tags = brief.get("top_tags") or []

    tag_line = ""
    if tags:
        joined = "&nbsp; |&nbsp; ".join(esc(t) for t in tags)
        tag_line = (
            f'<div style="font-size:11px;color:{_TAGS};margin-top:6px;'
            f'line-height:1.6;">{joined}</div>'
        )

    sub = f"{esc(subtitle)}&nbsp; |&nbsp; {esc(date_str)}" if date_str else esc(subtitle)
    return f"""
      <tr><td align="center" style="background:{_HEADER_BG};padding:20px 24px;">
        {_render_logo(brand)}
        <div style="font-size:13px;font-weight:bold;color:{_SUBTITLE};
                    margin-top:6px;letter-spacing:.5px;">{sub}</div>
        {tag_line}
      </td></tr>"""


def _render_category_bar(bar: Sequence) -> str:
    if not bar:
        return ""
    cells = "".join(
        f'<td align="center" style="background:{color};padding:5px;">'
        f'<span style="font-size:9px;font-weight:bold;color:#ffffff;'
        f'letter-spacing:.5px;">{esc(label)}</span></td>'
        for label, color in bar
    )
    return f"""
      <tr><td style="padding:14px 24px 0;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="2"
               style="width:100%;"><tr>{cells}</tr></table>
      </td></tr>"""


def _section_heading(text: str, accent: str, size: int = 14) -> str:
    return (
        f'<div style="border-bottom:2px solid {accent};margin:18px 0 10px;">'
        f'<div style="font-size:{size}px;font-weight:bold;color:{_INK};'
        f'padding-bottom:6px;">{esc(text)}</div></div>'
    )


def _render_exec(brief: Mapping[str, Any]) -> str:
    cards = brief.get("exec_cards") or []
    if not cards:
        return ""
    intro = brief.get("exec_intro", "")
    intro_html = (
        f'<div style="font-size:13px;font-style:italic;color:{_BODY};'
        f'margin-bottom:10px;">{esc(intro)}</div>' if intro else ""
    )

    rows = []
    for i in range(0, len(cards), 2):
        pair = cards[i:i + 2]
        tds = []
        for c in pair:
            color = c.get("color", BLUE)
            tds.append(
                f'<td width="50%" valign="top" style="width:50%;'
                f'border:1px solid {color};padding:9px 11px;">'
                f'<div style="font-size:9px;font-weight:bold;color:{color};'
                f'letter-spacing:.4px;margin-bottom:3px;">{esc(c.get("label",""))}</div>'
                f'<div style="font-size:10.5px;color:{_BODY};line-height:1.45;">'
                f'{esc(c.get("text",""))}</div></td>'
            )
        if len(tds) == 1:
            tds.append('<td width="50%" style="width:50%;"></td>')
        rows.append(f"<tr>{''.join(tds)}</tr>")

    return f"""
      <tr><td style="padding:16px 24px 0;">
        {_section_heading("EXECUTIVE SUMMARY", BLUE, size=15)}
        {intro_html}
        <table role="presentation" width="100%" cellpadding="0" cellspacing="6"
               style="width:100%;border-collapse:separate;">{''.join(rows)}</table>
      </td></tr>"""


def _byline_html(a: Mapping[str, Any]) -> str:
    journalist = _first(a, "journalist", "author", "byline", "reporter")
    pubs = _pub_list(a)
    pub = pubs[0] if pubs else "wire"
    if journalist:
        inner = (
            f'<span style="font-weight:bold;color:{BLUE};">{esc(pub)}</span>'
            f'<span style="color:{_MUTED};"> | {esc(journalist)}</span>'
        )
    else:
        inner = (f'<span style="font-style:italic;color:{_MUTED};">'
                 f'Syndicated by {esc(pub)}</span>')
    return f'<div style="font-size:10px;margin-bottom:4px;">{inner}</div>'


def _render_article(a: Mapping[str, Any]) -> str:
    title = _first(a, "title", "headline") or "(untitled)"
    url = _first(a, "url", "link", "href")
    summary = _truncate_words(_first(a, "summary", "description", "desc", "body"))
    extra = a.get("extra_html", "")

    if url:
        head = (
            f'<a href="{esc(url)}" target="_blank" '
            f'style="font-size:13px;font-weight:bold;color:{_LINK};'
            f'text-decoration:none;line-height:1.35;">{esc(title)}</a>'
        )
        link_block = (
            f'<div style="margin-bottom:5px;">'
            f'<a href="{esc(url)}" target="_blank" '
            f'style="font-size:10px;font-weight:bold;color:{BLUE};'
            f'text-decoration:none;">Read full story →</a></div>'
        )
    else:
        head = (
            f'<span style="font-size:13px;font-weight:bold;color:{_INK};'
            f'line-height:1.35;">{esc(title)}</span>'
        )
        link_block = ""

    return f"""
      <div style="border:1px solid {_HAIRLINE};padding:9px 12px;margin-bottom:8px;background:#ffffff;">
        {_byline_html(a)}
        <div style="margin:0 0 4px;">{head}</div>
        {link_block}
        <div style="font-size:12px;color:{_BODY};line-height:1.55;">{esc(summary)}</div>
        {extra}
      </div>"""


def _render_section(section: Mapping[str, Any]) -> str:
    name = section.get("name", "")
    accent = section.get("accent", BLUE)
    articles = list(section.get("articles") or [])
    if not articles:
        return ""
    body = "".join(_render_article(a) for a in articles)
    anchor_id = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
    return f"""
      <tr><td style="padding:6px 24px 0;">
        <a name="{anchor_id}"></a>
        {_section_heading(name, accent)}
        {body}
      </td></tr>"""


def _render_takeaways(brief: Mapping[str, Any]) -> str:
    items = brief.get("takeaways") or []
    if not items:
        return ""
    intro = brief.get("takeaways_intro", "")
    intro_html = (
        f'<div style="font-size:12px;font-style:italic;color:{_MUTED};'
        f'margin-bottom:8px;">{esc(intro)}</div>' if intro else ""
    )
    cards = []
    for i, t in enumerate(items, start=1):
        cards.append(f"""
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                 style="width:100%;margin-bottom:6px;">
            <tr>
              <td width="30" valign="top" align="center"
                  style="width:30px;background:{BLUE};padding:6px;">
                <span style="font-size:14px;font-weight:bold;color:#ffffff;">{i}</span>
              </td>
              <td valign="top" style="background:#f0f7ff;border:1px solid {_HAIRLINE};
                                      padding:6px 10px;">
                <div style="font-size:12px;font-weight:bold;color:{_INK};
                            margin-bottom:3px;">{esc(t.get("title",""))}</div>
                <div style="font-size:10px;color:{_BODY};line-height:1.5;">
                  {esc(t.get("text",""))}</div>
              </td>
            </tr>
          </table>""")
    return f"""
      <tr><td style="padding:6px 24px 0;">
        {_section_heading("STRATEGIC TAKEAWAYS", BLUE)}
        {intro_html}
        {''.join(cards)}
      </td></tr>"""


def _render_footer(brief: Mapping[str, Any]) -> str:
    name = brief.get("signoff_name", "")
    sub = brief.get("signoff_sub", "")
    covered = brief.get("sections_covered", "")
    disclaimer = brief.get("disclaimer", "")
    tags = brief.get("topic_tags") or []

    signoff = ""
    if name:
        covered_html = (
            f'<div style="font-size:8.5px;color:{_MUTED};margin-top:6px;'
            f'line-height:1.6;">Sections covered: {esc(covered)}</div>' if covered else ""
        )
        signoff = f"""
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                 style="width:100%;margin-top:14px;">
            <tr><td style="border:1px solid {BLUE};background:#eff6ff;padding:11px 14px;">
              <div style="font-size:12px;color:{_INK};">Warm Regards,</div>
              <div style="font-size:13px;font-weight:bold;color:{BLUE};margin-top:3px;">
                {esc(name)}</div>
              <div style="font-size:10px;font-style:italic;color:{_MUTED};margin-top:3px;">
                {esc(sub)}</div>
              {covered_html}
            </td></tr>
          </table>"""

    disc = ""
    if disclaimer:
        disc = (
            f'<div style="font-size:9px;font-weight:bold;color:{_MUTED};margin-top:14px;">'
            f'DISCLAIMER:</div>'
            f'<div style="font-size:8.5px;font-style:italic;color:{_MUTED};'
            f'line-height:1.5;margin-top:2px;">{esc(disclaimer)}</div>'
        )

    tag_html = ""
    if tags:
        chips = "&nbsp; ".join(
            f'<span style="color:#1d4ed8;background:#eff6ff;">{esc(t)}</span>'
            for t in tags
        )
        tag_html = (
            f'<div style="font-size:9px;font-weight:bold;color:{BLUE};margin-top:12px;">'
            f'TOPIC TAGS:</div>'
            f'<div style="font-size:8.5px;line-height:1.9;margin-top:2px;">{chips}</div>'
        )

    return f"""
      <tr><td style="padding:8px 24px 24px;">{signoff}{disc}{tag_html}</td></tr>"""


# --------------------------------------------------------------------------- #
# Master renderers                                                             #
# --------------------------------------------------------------------------- #
def _render_bookmarks_bar(sections: Sequence) -> str:
    if not sections:
        return ""
    links = []
    for s in sections:
        name = s.get("name", "")
        if not name:
            continue
        anchor_id = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
        links.append(f'<a href="#{anchor_id}" style="color:{BLUE}; text-decoration:none; font-weight:bold; font-size:10px;">{esc(name)}</a>')
    
    if not links:
        return ""
        
    cells = " &nbsp;|&nbsp; ".join(links)
    return f"""
      <tr><td align="center" style="background:#f3f4f6; padding:8px 24px; border-bottom:1px solid {_HAIRLINE};">
        <div style="font-size:10px; color:{_MUTED}; line-height:1.5;">
          {cells}
        </div>
      </td></tr>"""


def render_brief_html(brief: Mapping[str, Any]) -> str:
    sections_html = "".join(_render_section(s) for s in (brief.get("sections") or []))
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f4f5f7;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
         style="background:#f4f5f7;padding:20px 10px;">
    <tr><td align="center">
      <table role="presentation" width="{_MAX_W}" cellpadding="0" cellspacing="0"
             style="max-width:{_MAX_W}px;width:100%;background:#ffffff;
             font-family:{_FONT};">
        {_render_header(brief)}
        {_render_bookmarks_bar(brief.get("sections") or [])}
        {_render_category_bar(brief.get("category_bar") or [])}
        {_render_exec(brief)}
        {_render_takeaways(brief)}
        {sections_html}
        {_render_footer(brief)}
      </table>
    </td></tr>
  </table>
</body></html>"""


def render_brief_text(brief: Mapping[str, Any]) -> str:
    """Plain-text fallback."""
    out = [brief.get("brand", ""), brief.get("subtitle", ""),
           brief.get("date_str", ""), "=" * 60, ""]
    if brief.get("exec_intro"):
        out += ["EXECUTIVE SUMMARY", brief["exec_intro"], ""]
        for c in brief.get("exec_cards") or []:
            out.append(f"- {c.get('label','')}: {c.get('text','')}")
        out.append("")
    for s in brief.get("sections") or []:
        arts = s.get("articles") or []
        if not arts:
            continue
        out += [f"## {s.get('name','').upper()}", ""]
        for a in arts:
            out.append(_byline(a))
            out.append(_first(a, "title", "headline"))
            u = _first(a, "url", "link")
            if u:
                out.append(u)
            out.append(_truncate_words(_first(a, "summary", "description")))
            out.append("")
    return "\n".join(out)
