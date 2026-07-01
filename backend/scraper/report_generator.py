import os
from datetime import datetime
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn, nsmap
import docx

# Register VML namespaces for horizontal vector shapes
nsmap['v'] = 'urn:schemas-microsoft-com:vml'
nsmap['o'] = 'urn:schemas-microsoft-com:office:office'

def add_horizontal_line(paragraph):
    """Adds a thin template-matching horizontal divider line to the paragraph using paragraph bottom border."""
    pPr = paragraph._p.get_or_add_pPr()
    pBdr = pPr.find(qn('w:pBdr'))
    if pBdr is None:
        pBdr = OxmlElement('w:pBdr')
        pPr.append(pBdr)
    else:
        bottom_existing = pBdr.find(qn('w:bottom'))
        if bottom_existing is not None:
            pBdr.remove(bottom_existing)
            
    bottom = OxmlElement('w:bottom')
    bottom.set(qn('w:val'), 'single')
    bottom.set(qn('w:sz'), '12')  # 1.5pt width
    bottom.set(qn('w:space'), '12')  # Spacing below the paragraph
    bottom.set(qn('w:color'), 'D3D3D3')  # Light grey
    pBdr.append(bottom)

def add_hyperlink(paragraph, url, text, color="1155cc", underline=True):
    """
    Inserts a clickable hyperlink run into a paragraph.
    """
    part = paragraph.part
    r_id = part.relate_to(url, docx.opc.constants.RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
    
    hyperlink = OxmlElement('w:hyperlink')
    hyperlink.set(qn('r:id'), r_id)
    
    new_run = OxmlElement('w:r')
    rPr = OxmlElement('w:rPr')
    
    if color:
        c = OxmlElement('w:color')
        c.set(qn('w:val'), color)
        rPr.append(c)
        
    if underline:
        u = OxmlElement('w:u')
        u.set(qn('w:val'), 'single')
        rPr.append(u)
        
    # Apply Calibri Font & Size 10pt
    rFonts = OxmlElement('w:rFonts')
    rFonts.set(qn('w:ascii'), 'Calibri')
    rFonts.set(qn('w:hAnsi'), 'Calibri')
    rPr.append(rFonts)
    
    sz = OxmlElement('w:sz')
    sz.set(qn('w:val'), '20')  # 10pt
    rPr.append(sz)
    
    # Bold headline
    bold = OxmlElement('w:b')
    rPr.append(bold)
    
    new_run.append(rPr)
    text_node = OxmlElement('w:t')
    text_node.text = text
    new_run.append(text_node)
    
    hyperlink.append(new_run)
    paragraph._p.append(hyperlink)
    return hyperlink

def generate_docx_report(client_name: str, date_str: str, data: dict, output_path: str, template_path: str = None) -> str:
    """
    Generates a professionally formatted DOCX report for a client with outline headers & hyperlinked headlines.
    Matches the format of the provided reference Scapia Tracker.docx document.
    """
    # Ensure directory exists
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    if template_path and os.path.exists(template_path):
        doc = Document(template_path)
    else:
        doc = Document()
        
    # Set default margins if new document
    if not template_path:
        for section in doc.sections:
            section.top_margin = Inches(1)
            section.bottom_margin = Inches(1)
            section.left_margin = Inches(1)
            section.right_margin = Inches(1)

    # 1. Add Logo at the top if it exists in the backend static folder
    logo_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "logo.png")
    if os.path.exists(logo_path):
        logo_p = doc.add_paragraph()
        logo_p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        logo_p.paragraph_format.space_before = Pt(0)
        logo_p.paragraph_format.space_after = Pt(12)
        logo_run = logo_p.add_run()
        logo_run.add_picture(logo_path, width=docx.shared.Emu(1047750)) # Exact width from Scapia Tracker.docx (1.15 inches)

    # Format date to Option A: "17 June 2026"
    clean_date_str = date_str
    try:
        # Check if incoming format is "Month DD, YYYY" (e.g. "June 17, 2026")
        dt = datetime.strptime(date_str, "%B %d, %Y")
        clean_date_str = dt.strftime("%d %B %Y")
    except Exception:
        try:
            # Check if ISO date
            dt = datetime.fromisoformat(date_str)
            clean_date_str = dt.strftime("%d %B %Y")
        except Exception:
            pass

    # Document Header: Heading 1 style to automatically map to outline navigation tabs in Google Docs
    title_p = doc.add_paragraph(style='Heading 1')
    title_run = title_p.add_run(clean_date_str)
    title_run.font.name = 'Calibri'
    title_run.font.size = Pt(14)
    title_run.font.bold = True
    title_run.font.color.rgb = RGBColor(0, 0, 0)
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_p.paragraph_format.space_after = Pt(12)

    # Write each section
    for section_name, articles in data.items():
        # Section Heading styled manually (not Heading style) so it doesn't map to outline nested under the date
        section_p = doc.add_paragraph()
        section_run = section_p.add_run(section_name)
        section_run.font.name = 'Calibri'
        section_run.font.size = Pt(10)
        section_run.font.bold = True
        section_run.font.color.rgb = RGBColor(0, 0, 0)
        section_p.paragraph_format.space_before = Pt(12)
        section_p.paragraph_format.space_after = Pt(12)

        if not articles:
            no_art_p = doc.add_paragraph()
            no_art_run = no_art_p.add_run("No relevant articles found for this section.")
            no_art_run.font.name = 'Calibri'
            no_art_run.font.size = Pt(10)
            no_art_run.font.italic = True
            no_art_p.paragraph_format.space_before = Pt(12)
            no_art_p.paragraph_format.space_after = Pt(12)
            continue

        # Group articles by category (A, B, or C)
        from scraper.search_utils import match_publication_category
        grouped_articles = {"A": [], "B": [], "C": []}
        for article in articles:
            cat = article.get("publication_category")
            if not cat:
                cat = match_publication_category(article.get("agency"), article.get("url") or article.get("resolved_url"))
            if cat not in ["A", "B", "C"]:
                cat = "C"
            grouped_articles[cat].append(article)

        # Write grouped categories
        for cat_name in ["A", "B", "C"]:
            cat_list = grouped_articles[cat_name]
            if not cat_list:
                continue

            # Sub-heading for Category
            cat_p = doc.add_paragraph()
            cat_run = cat_p.add_run(f"Category {cat_name} Publications")
            cat_run.font.name = 'Calibri'
            cat_run.font.size = Pt(10)
            cat_run.font.bold = True
            cat_run.font.italic = True
            cat_run.font.color.rgb = RGBColor(120, 120, 120)
            cat_p.paragraph_format.space_before = Pt(12)
            cat_p.paragraph_format.space_after = Pt(12)

            for i, article in enumerate(cat_list):
                title = article.get("title", "No Title")
                agency = article.get("agency") or "Unknown Publication"
                summary = article.get("summary") or "No summary available."
                url = article.get("url") or article.get("resolved_url") or "#"
                
                # Single paragraph for the entire article block (Calibri 10pt)
                art_p = doc.add_paragraph()
                art_p.paragraph_format.space_before = Pt(12)
                art_p.paragraph_format.space_after = Pt(12)
                art_p.paragraph_format.line_spacing = 1.15
                
                # 1. Headline (Hyperlink)
                try:
                    add_hyperlink(art_p, url, title, color="1155cc", underline=True)
                except Exception:
                    # Fallback to plain text if hyperlink XML injection fails
                    fallback_run = art_p.add_run(title)
                    fallback_run.font.name = 'Calibri'
                    fallback_run.font.size = Pt(10)
                    fallback_run.font.bold = True
                    fallback_run.font.color.rgb = RGBColor(17, 85, 204)
                
                # Paywall tag (if applicable)
                if article.get("is_paywalled"):
                    pw_run = art_p.add_run("  🔒 Paywalled")
                    pw_run.font.name = 'Calibri'
                    pw_run.font.size = Pt(9)
                    pw_run.font.bold = True
                    pw_run.font.color.rgb = RGBColor(204, 102, 0)
                
                # Publication name on same line (Bold, black, separated by " - ")
                pub_run = art_p.add_run(f" - {agency}\n\n")
                pub_run.font.name = 'Calibri'
                pub_run.font.size = Pt(10)
                pub_run.font.bold = True
                pub_run.font.color.rgb = RGBColor(0, 0, 0)
                
                # 2. Summary Content (Second line onwards)
                sum_run = art_p.add_run(summary)
                sum_run.font.name = 'Calibri'
                sum_run.font.size = Pt(10)
                sum_run.font.color.rgb = RGBColor(0, 0, 0)
                
                # Thin divider line between articles within the category
                if i < len(cat_list) - 1:
                    add_horizontal_line(art_p)
                
    # Save the document
    doc.save(output_path)
    return output_path


def generate_organized_docx_report(client_name: str, report_type: str, date_str: str, grouped_data: dict, output_path: str) -> str:
    """
    Generates a professionally formatted DOCX report grouped by Master Heading and Sub Heading.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    doc = Document()
    
    for section in doc.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)

    # Add Title
    title_p = doc.add_paragraph()
    title_run = title_p.add_run(f"NEXUS NEWS BRIEFING: {report_type.upper()}")
    title_run.font.name = 'Calibri'
    title_run.font.size = Pt(18)
    title_run.font.bold = True
    title_run.font.color.rgb = RGBColor(74, 134, 232)
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Add Subtitle / Date
    sub_p = doc.add_paragraph()
    sub_run = sub_p.add_run(f"Date: {date_str} | Generated for {client_name}")
    sub_run.font.name = 'Calibri'
    sub_run.font.size = Pt(11)
    sub_run.font.italic = True
    sub_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Divider line
    divider = doc.add_paragraph()
    add_horizontal_line(divider)

    if not grouped_data:
        empty_p = doc.add_paragraph()
        empty_run = empty_p.add_run("No relevant articles found for this briefing.")
        empty_run.font.name = 'Calibri'
        empty_run.font.size = Pt(11)
        doc.save(output_path)
        return output_path

    # Iterate over Master Headings
    for master, subs in grouped_data.items():
        # Add Master Heading (H1)
        m_p = doc.add_paragraph()
        m_run = m_p.add_run(master)
        m_run.font.name = 'Calibri'
        m_run.font.size = Pt(14)
        m_run.font.bold = True
        m_run.font.color.rgb = RGBColor(74, 134, 232)
        m_p.paragraph_format.space_before = Pt(18)
        m_p.paragraph_format.space_after = Pt(6)
        m_p.paragraph_format.keep_with_next = True

        for sub, articles in subs.items():
            if not articles:
                continue
            # Add Sub Heading (H2)
            s_p = doc.add_paragraph()
            s_run = s_p.add_run(sub)
            s_run.font.name = 'Calibri'
            s_run.font.size = Pt(12)
            s_run.font.bold = True
            s_run.font.color.rgb = RGBColor(102, 102, 102)
            s_p.paragraph_format.space_before = Pt(12)
            s_p.paragraph_format.space_after = Pt(4)
            s_p.paragraph_format.keep_with_next = True

            for i, art in enumerate(articles):
                # Add Article Headline as clickable link
                art_p = doc.add_paragraph()
                art_p.paragraph_format.space_before = Pt(6)
                art_p.paragraph_format.space_after = Pt(2)
                
                title_text = art.get("title", "Untitled Article")
                url = art.get("url", "#")
                
                try:
                    add_hyperlink(art_p, url, title_text, color="1155cc", underline=True)
                except Exception:
                    fallback_run = art_p.add_run(title_text)
                    fallback_run.font.name = 'Calibri'
                    fallback_run.font.size = Pt(10)
                    fallback_run.font.bold = True
                    fallback_run.font.color.rgb = RGBColor(17, 85, 204)
                
                # Add Publication, Author (if available), and Date
                meta_p = doc.add_paragraph()
                meta_p.paragraph_format.space_before = Pt(0)
                meta_p.paragraph_format.space_after = Pt(8)
                
                pub_name = art.get("agency") or "Unknown Publication"
                pub_author = art.get("author")
                pub_date = art.get("published_at")
                
                date_text = ""
                if pub_date:
                    if isinstance(pub_date, str):
                        date_text = pub_date[:10]
                    else:
                        date_text = pub_date.strftime("%Y-%m-%d")
                
                conf_score = art.get("confidence_score", 0)
                if pub_author and str(pub_author).strip():
                    meta_text = f"Publication: {pub_name} | Author: {str(pub_author).strip()} | Date: {date_text} | Relevance Confidence: {conf_score}/10"
                else:
                    meta_text = f"Publication: {pub_name} | Date: {date_text} | Relevance Confidence: {conf_score}/10"
                
                meta_run = meta_p.add_run(meta_text)
                meta_run.font.name = 'Calibri'
                meta_run.font.size = Pt(9.5)
                meta_run.font.italic = True
                meta_run.font.color.rgb = RGBColor(128, 128, 128)
                
                # Thin divider line between articles
                if i < len(articles) - 1:
                    add_horizontal_line(meta_p)
                
    doc.save(output_path)
    return output_path
