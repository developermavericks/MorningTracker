import os
from datetime import datetime
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

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

def generate_docx_report(client_name: str, date_str: str, data: dict, output_path: str, template_path: str = None) -> str:
    """
    Generates a professionally formatted DOCX report for a client.
    
    Parameters:
      client_name: Name of the client (e.g. Scapia)
      date_str: Date string for the report
      data: Dict of {section_name: [list of article dicts]}
      output_path: Where to save the generated docx file
      template_path: Optional path to a base docx template to copy styling from
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

    # Document Header: Centered, Underlined, CLIENT | Date
    title_p = doc.add_paragraph()
    title_run = title_p.add_run(f"{client_name.upper()} | {date_str}")
    title_run.font.name = 'Arial'
    title_run.font.size = Pt(16)
    title_run.font.bold = True
    title_run.font.underline = True
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_p.paragraph_format.space_after = Pt(18)

    # Write each section
    for section_name, articles in data.items():
        if not articles:
            continue
            
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

        for i, article in enumerate(articles):
            title = article.get("title", "No Title")
            agency = article.get("agency") or "Unknown Publication"
            summary = article.get("summary") or "No summary available."
            url = article.get("url") or article.get("resolved_url") or "#"
            
            # Single paragraph for the entire article block to avoid large spacing gaps
            art_p = doc.add_paragraph()
            art_p.paragraph_format.space_before = Pt(8)
            art_p.paragraph_format.space_after = Pt(10)
            art_p.paragraph_format.line_spacing = 1.15
            
            # 1. Link (First line)
            link_run = art_p.add_run(url + "\n")
            link_run.font.name = 'Arial'
            link_run.font.size = Pt(9.5)
            link_run.font.color.rgb = RGBColor(0, 102, 204)  # Deep blue link color
            link_run.font.underline = True
            
            # 2. Headline (Second line)
            title_run = art_p.add_run(title)
            title_run.font.name = 'Arial'
            title_run.font.size = Pt(11)
            title_run.font.bold = True
            title_run.font.color.rgb = RGBColor(0, 0, 0)
            
            # Publication on the same line as the Headline
            pub_run = art_p.add_run(f" — {agency}\n")
            pub_run.font.name = 'Arial'
            pub_run.font.size = Pt(9.5)
            pub_run.font.italic = True
            pub_run.font.color.rgb = RGBColor(120, 120, 120)
            
            # 3. Summary Content (Third line onwards)
            sum_run = art_p.add_run(summary)
            sum_run.font.name = 'Arial'
            sum_run.font.size = Pt(9.5)
            sum_run.font.color.rgb = RGBColor(60, 60, 60)
            
            # Thin divider line between articles (but not after the last article of the section)
            if i < len(articles) - 1:
                add_horizontal_line(art_p)
                
    # Save the document
    doc.save(output_path)
    return output_path
