import os
from datetime import datetime
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
import docx

def add_horizontal_line(paragraph):
    """Adds a thin bottom border to a paragraph (horizontal divider line)."""
    pPr = paragraph._p.get_or_add_pPr()
    pBdr = OxmlElement('w:pBdr')
    bottom = OxmlElement('w:bottom')
    bottom.set(qn('w:val'), 'single')
    bottom.set(qn('w:sz'), '6')  # Size 6 = 3/4 pt
    bottom.set(qn('w:space'), '12')
    bottom.set(qn('w:color'), 'D3D3D3')  # Light grey
    pBdr.append(bottom)
    pPr.append(pBdr)

def add_hyperlink(paragraph, url, text, color="0066CC", underline=True):
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
        
    # Apply Arial Font & Size 11pt
    rFonts = OxmlElement('w:rFonts')
    rFonts.set(qn('w:ascii'), 'Arial')
    rFonts.set(qn('w:hAnsi'), 'Arial')
    rPr.append(rFonts)
    
    sz = OxmlElement('w:sz')
    sz.set(qn('w:val'), '22')  # 11pt
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

    # Document Header: Heading 1 style to automatically map to outline navigation tabs in Google Docs
    title_p = doc.add_paragraph(style='Heading 1')
    title_run = title_p.add_run(f"{client_name.upper()} | {date_str}")
    title_run.font.name = 'Arial'
    title_run.font.size = Pt(16)
    title_run.font.bold = True
    title_run.font.color.rgb = RGBColor(0, 0, 0)
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_p.paragraph_format.space_after = Pt(18)

    # Write each section
    for section_name, articles in data.items():
        # Section Heading
        section_p = doc.add_paragraph()
        section_run = section_p.add_run(section_name)
        section_run.font.name = 'Arial'
        section_run.font.size = Pt(13)
        section_run.font.bold = True
        section_run.font.color.rgb = RGBColor(18, 53, 91)
        section_p.paragraph_format.space_before = Pt(18)
        section_p.paragraph_format.space_after = Pt(6)
        
        # Divider line under section header
        add_horizontal_line(section_p)

        if not articles:
            no_art_p = doc.add_paragraph()
            no_art_run = no_art_p.add_run("No relevant articles found for this section.")
            no_art_run.font.name = 'Arial'
            no_art_run.font.size = Pt(10)
            no_art_run.font.italic = True
            no_art_p.paragraph_format.space_before = Pt(6)
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
            cat_run.font.name = 'Arial'
            cat_run.font.size = Pt(11)
            cat_run.font.bold = True
            cat_run.font.italic = True
            cat_run.font.color.rgb = RGBColor(120, 120, 120)
            cat_p.paragraph_format.space_before = Pt(10)
            cat_p.paragraph_format.space_after = Pt(4)

            for i, article in enumerate(cat_list):
                title = article.get("title", "No Title")
                agency = article.get("agency") or "Unknown Publication"
                summary = article.get("summary") or "No summary available."
                url = article.get("url") or article.get("resolved_url") or "#"
                
                # Single paragraph for the entire article block to avoid large spacing gaps
                art_p = doc.add_paragraph()
                art_p.paragraph_format.space_before = Pt(8)
                art_p.paragraph_format.space_after = Pt(10)
                art_p.paragraph_format.line_spacing = 1.15
                
                # 1. Headline (Hyperlink)
                try:
                    add_hyperlink(art_p, url, title, color="0066CC", underline=True)
                except Exception as e:
                    # Fallback to plain text if hyperlink XML injection fails
                    fallback_run = art_p.add_run(title)
                    fallback_run.font.name = 'Arial'
                    fallback_run.font.size = Pt(11)
                    fallback_run.font.bold = True
                    fallback_run.font.color.rgb = RGBColor(0, 102, 204)
                
                # Publication name on same line
                pub_run = art_p.add_run(f" — {agency}\n")
                pub_run.font.name = 'Arial'
                pub_run.font.size = Pt(9.5)
                pub_run.font.italic = True
                pub_run.font.color.rgb = RGBColor(120, 120, 120)
                
                # 2. Summary Content (Second line onwards)
                sum_run = art_p.add_run(summary)
                sum_run.font.name = 'Arial'
                sum_run.font.size = Pt(9.5)
                sum_run.font.color.rgb = RGBColor(60, 60, 60)
                
                # Thin divider line between articles within the category
                if i < len(cat_list) - 1:
                    add_horizontal_line(art_p)
                
    # Save the document
    doc.save(output_path)
    return output_path
