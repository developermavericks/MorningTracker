import os
import csv
import sys
import re
import openpyxl

# Increase CSV field size limit to handle large text blocks
max_limit = sys.maxsize
while True:
    try:
        csv.field_size_limit(max_limit)
        break
    except OverflowError:
        max_limit = int(max_limit // 10)

# --- Configuration -----------------------------------------------------------
INPUT_CSV = r"E:\MAVERICKS\Heavy_automation_pooja_codefiles\filtered_priority_only.csv"
KEYWORDS_XLSX = r"E:\MAVERICKS\Heavy_automation_pooja_codefiles\keywords.xlsx"
OUTPUT_MATCHED = r"E:\MAVERICKS\Heavy_automation_pooja_codefiles\keyword_matched_articles.csv"
OUTPUT_UNMATCHED = r"E:\MAVERICKS\Heavy_automation_pooja_codefiles\keyword_unmatched_articles.csv"


# --- Step 1: Parse keywords.xlsx into sector -> keywords mapping -------------

def parse_keywords_file(xlsx_path):
    """
    Parse the keywords Excel file and return a dict:
        {
            sector_name: {
                sub_category: [keyword1, keyword2, ...],
                ...
            },
            ...
        }

    The Excel has this layout:
      - Sector header rows (no numeric serial, text in col A, nothing useful in col B
        OR col B says 'Keywords' / 'Keywords (Use Boolean...)')
      - Under each sector: rows like 'Company Keywords', 'Competition Brand Keywords',
        'Industry Keywords' in col A, with comma-separated keywords in col B.
      - Blank rows separate sectors.
    """
    wb = openpyxl.load_workbook(xlsx_path)
    ws = wb.active

    # Identify sector header labels (col A values that mark a new sector)
    # These are rows where col B is None or contains just 'Keywords' / header text
    SUBCATEGORY_LABELS = {
        "brand names", "india-specific", "common misspellings",
        "leadership/personnel", "company keywords", "competition keywords",
        "competition brand keywords", "industry keywords", "competitor keywords",
    }

    sectors = {}           # sector_name -> { sub_cat -> [keywords] }
    current_sector = None

    for row in ws.iter_rows(min_row=1, values_only=True):
        col_a = str(row[0]).strip() if row[0] else ""
        col_b = str(row[1]).strip() if row[1] else ""

        # Skip entirely empty rows
        if not col_a and not col_b:
            continue

        col_a_lower = col_a.lower().strip()

        # Detect if this row is a SECTOR HEADER
        # Sector headers have text in col A and either:
        #   - col B is empty, or
        #   - col B is literally 'Keywords' or starts with 'Keywords ('
        is_sector_header = False
        if col_a and col_a_lower not in SUBCATEGORY_LABELS:
            if (not col_b
                or col_b.lower() == "keywords"
                or col_b.lower().startswith("keywords (")):
                is_sector_header = True

        if is_sector_header:
            current_sector = col_a.strip()
            if current_sector not in sectors:
                sectors[current_sector] = {}
            continue

        # Detect if this row is a SUB-CATEGORY row with keywords
        if col_a_lower in SUBCATEGORY_LABELS and col_b:
            sub_cat = col_a.strip()
            keywords = extract_keywords(col_b)
            if current_sector and keywords:
                if sub_cat not in sectors[current_sector]:
                    sectors[current_sector][sub_cat] = []
                sectors[current_sector][sub_cat].extend(keywords)
            continue

        # Some rows have a product name in col A and keywords directly in col B
        # (e.g. 'Youtube keywords', 'Google Maps keywords', 'Google Pay keywords')
        if col_a and col_b and col_a_lower not in SUBCATEGORY_LABELS:
            # This is a product-specific keyword row within the current sector
            keywords = extract_keywords(col_b)
            if current_sector and keywords:
                sub_cat = col_a.strip()
                if sub_cat not in sectors[current_sector]:
                    sectors[current_sector][sub_cat] = []
                sectors[current_sector][sub_cat].extend(keywords)

    return sectors


def extract_keywords(raw_text):
    """
    Extract individual keywords/phrases from a comma-separated string.
    Handles quoted phrases, curly quotes, newlines, and '+' operators.
    Returns a list of cleaned keyword phrases (lowercased).
    """
    if not raw_text:
        return []

    # Normalize various quote characters
    text = raw_text
    for ch in ['\u201c', '\u201d', '\u2018', '\u2019', '\u00ab', '\u00bb']:
        text = text.replace(ch, '"')

    # Remove boolean operators like AND, OR, NEAR/N that are instructions, not keywords
    text = re.sub(r'\bAND\b', ' ', text)
    text = re.sub(r'\bOR\b', ' ', text)
    text = re.sub(r'\bNEAR/\d+\b', ' ', text)

    # Split by comma (primary delimiter)
    parts = text.split(',')

    keywords = []
    for part in parts:
        # Remove quotes and extra whitespace
        kw = part.strip().strip('"').strip("'").strip()
        # Remove newlines within keyword
        kw = kw.replace('\n', ' ').replace('\r', ' ')
        # Collapse multiple spaces
        kw = re.sub(r'\s+', ' ', kw).strip()
        # Remove trailing/leading punctuation artifacts
        kw = kw.strip(',').strip('"').strip("'").strip()

        # Skip empty, too-short, or header-like entries
        if not kw or len(kw) < 2:
            continue
        if kw.lower().startswith('keywords'):
            continue
        # Skip entries that are just parenthetical notes
        if kw.startswith('(') and kw.endswith(')'):
            continue

        # Handle '+' operator: "Smartwatch + India" -> "smartwatch india"
        # The '+' in the Excel means both words should appear
        kw_clean = kw.replace(' + ', ' ').replace('+', ' ')
        kw_clean = re.sub(r'\s+', ' ', kw_clean).strip()

        if len(kw_clean) >= 2:
            keywords.append(kw_clean.lower())

    return keywords


# --- Step 2: Build a flat list of (keyword, sector, sub_category) tuples -----

def build_keyword_index(sectors):
    """
    Returns a list of (keyword_lower, sector, sub_category) for matching.
    Keywords are sorted longest-first so longer matches take priority.
    """
    index = []
    for sector, sub_cats in sectors.items():
        for sub_cat, kw_list in sub_cats.items():
            for kw in kw_list:
                index.append((kw, sector, sub_cat))

    # Sort longest keyword first (greedy matching)
    index.sort(key=lambda x: -len(x[0]))
    return index


# --- Step 3: Match article titles against keywords --------------------------

def match_title(title, keyword_index):
    """
    Check if any keyword appears in the title (case-insensitive).
    For multi-word keywords with '+' (now spaces), ALL words must appear.
    Returns (matched_keyword, sector, sub_category) or (None, None, None).
    """
    title_lower = title.lower()

    for kw, sector, sub_cat in keyword_index:
        words = kw.split()
        if len(words) > 1:
            # All words must appear in the title
            if all(w in title_lower for w in words):
                return kw, sector, sub_cat
        else:
            # Single word/phrase: check if it appears as-is in the title
            # Use word boundary matching for very short keywords (<=3 chars)
            if len(kw) <= 3:
                if re.search(r'\b' + re.escape(kw) + r'\b', title_lower):
                    return kw, sector, sub_cat
            else:
                if kw in title_lower:
                    return kw, sector, sub_cat

    return None, None, None


# --- Step 4: Main processing ------------------------------------------------

def filter_by_keywords(input_csv, keywords_xlsx, output_matched, output_unmatched):
    # Parse keywords
    print("Loading keywords from Excel...")
    sectors = parse_keywords_file(keywords_xlsx)

    total_keywords = 0
    for sector, sub_cats in sectors.items():
        print(f"\n  Sector: {sector}")
        for sub_cat, kw_list in sub_cats.items():
            unique_kws = list(set(kw_list))
            sectors[sector][sub_cat] = unique_kws
            print(f"    {sub_cat}: {len(unique_kws)} keywords")
            total_keywords += len(unique_kws)

    print(f"\nTotal keywords loaded: {total_keywords}")

    # Build index
    keyword_index = build_keyword_index(sectors)

    # Process CSV
    print(f"\nProcessing articles from: {input_csv}")

    total = 0
    matched_count = 0
    unmatched_count = 0
    sector_stats = {}  # sector -> count

    with open(input_csv, 'r', encoding='utf-8-sig', errors='replace') as infile, \
         open(output_matched, 'w', encoding='utf-8', newline='') as out_m, \
         open(output_unmatched, 'w', encoding='utf-8', newline='') as out_u:

        reader = csv.reader(infile)
        header = next(reader)

        # Add Matched_Keyword, Sector, Sub_Category columns to matched output
        matched_header = header + ['Matched_Keyword', 'Sector', 'Sub_Category']
        writer_m = csv.writer(out_m)
        writer_u = csv.writer(out_u)
        writer_m.writerow(matched_header)
        writer_u.writerow(header)

        # Find the Title column index
        try:
            title_idx = header.index('Title')
        except ValueError:
            print("ERROR: 'Title' column not found!")
            print(f"Available columns: {header}")
            return

        for row in reader:
            total += 1
            title = row[title_idx] if title_idx < len(row) else ""

            kw, sector, sub_cat = match_title(title, keyword_index)

            if kw:
                writer_m.writerow(row + [kw, sector, sub_cat])
                matched_count += 1
                sector_stats[sector] = sector_stats.get(sector, 0) + 1
            else:
                writer_u.writerow(row)
                unmatched_count += 1

    # Summary
    print("\n" + "=" * 65)
    print("KEYWORD FILTERING COMPLETE")
    print("=" * 65)
    print(f"Total articles processed:        {total}")
    print(f"Keyword-matched articles:        {matched_count}")
    print(f"Unmatched articles (filtered):   {unmatched_count}")
    print(f"\nMatched articles saved to:   {output_matched}")
    print(f"Unmatched articles saved to: {output_unmatched}")

    if sector_stats:
        print("\n--- Matches by Sector ---")
        for sector, count in sorted(sector_stats.items(), key=lambda x: -x[1]):
            print(f"  {sector:<55} {count:>5}")


if __name__ == "__main__":
    filter_by_keywords(INPUT_CSV, KEYWORDS_XLSX, OUTPUT_MATCHED, OUTPUT_UNMATCHED)
