import os
import csv
import sys
import openpyxl

# Increase CSV field size limit to handle large text blocks in 'Full Body'
max_limit = sys.maxsize
while True:
    try:
        csv.field_size_limit(max_limit)
        break
    except OverflowError:
        max_limit = int(max_limit // 10)

# ─── Configuration ───────────────────────────────────────────────────────────
INPUT_CSV = r"E:\MAVERICKS\Heavy_automation_pooja_codefiles\final.csv"
PRIORITY_LIST_XLSX = r"E:\MAVERICKS\Heavy_automation_pooja_codefiles\[Internal] Google Online Priority Media List 2026.xlsx"
OUTPUT_CSV = r"E:\MAVERICKS\Heavy_automation_pooja_codefiles\filtered_non_priority.csv"
PRIORITY_OUTPUT_CSV = r"E:\MAVERICKS\Heavy_automation_pooja_codefiles\filtered_priority_only.csv"


def load_priority_publications(xlsx_path):
    """
    Read the priority media list from the Excel file.
    Returns a set of normalised publication names and a list of original names.
    """
    wb = openpyxl.load_workbook(xlsx_path)
    ws = wb.active

    publications_original = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        serial, name, *_ = (list(row) + [None, None])[:3]
        if name and isinstance(serial, (int, float)):
            # Clean up multi-line entries like "BloombergQuint\n(now NDTV Profit)"
            clean_name = name.strip().split("\n")[0].strip()
            publications_original.append(clean_name)

    print(f"Loaded {len(publications_original)} priority publications from Excel:")
    for pub in publications_original:
        print(f"  • {pub}")

    return publications_original


def build_match_keywords(publications):
    """
    Build a list of (keyword, original_name) pairs for flexible matching.
    Each keyword is a lowercased, stripped version used for substring checks.
    We also add known alias mappings from CSV agency names.
    """
    # Known aliases: maps priority list name -> list of additional CSV agency patterns
    known_aliases = {
        "PTI":                   ["pti"],
        "IANS":                  ["ians"],
        "ANI":                   ["ani news"],
        "Reuters India":         ["reuters"],
        "NDTV":                  ["ndtv"],
        "BloombergQuint":        ["ndtv profit"],
        "NDTV Gadgets360":       ["gadgets 360", "gadgets360"],
        "Gadgets Now":           ["gadgets now", "gadgetsnow"],
        "Moneycontrol":          ["moneycontrol"],
        "91Mobiles":             ["91mobiles"],
        "Analytics India":       ["analytics india", "aim media house"],
        "Digit":                 ["digit.in"],
        "YourStory":             ["yourstory"],
        "India Times":           ["indiatimes"],
        "The Print":             ["theprint"],
        "TechCircle":            ["techcircle"],
        "VCCircle":              ["vccircle"],
        "Scroll.in":             ["scroll.in", "scroll"],
        "Aaj Tak":               ["aaj tak", "aajtak"],
        "News18":                ["news18"],
        "Mint":                  ["mint", "livemint"],
        "The Financial Express": ["financial express", "financialexpress"],
        "Business Standard":     ["business standard"],
        "Outlook India":         ["outlook india"],
        "Outlook Business":      ["outlook business", "outlookbusiness"],
        "BW BusinessWorld":      ["bw businessworld", "bw business"],
        "Inc42":                 ["inc42"],
        "Forbes India":          ["forbes india"],
        "Fortune India":         ["fortune india"],
        "Business Today":        ["business today"],
        "Business India":        ["business india"],
        "The Ken":               ["the ken"],
        "The Quint":             ["the quint", "thequint"],
        "The Morning Context":   ["the morning context"],
        "Deccan Herald":         ["deccan herald"],
        "Deccan Chronicle":      ["deccan chronicle"],
        "India Today":           ["india today"],
        "ET BrandEquity":        ["et brandequity", "brandequity"],
        "afaqs!":                ["afaqs"],
        "Exchange4Media":        ["exchange4media"],
        "Medianama":             ["medianama"],
        "Amar Ujala":            ["amar ujala"],
        "Dainik Bhaskar":        ["dainik bhaskar"],
        "Bhaskar Hindi":         ["bhaskar hindi"],
        "Bhaskar Live":          ["bhaskar live"],
        "Dainik Jagran":         ["dainik jagran", "daily jagran", "jagran"],
        "Navbharat Times":       ["navbharat times"],
        "DT Next":               ["dt next"],
        "Mumbai Mirror":         ["mumbai mirror"],
        "The Hindu":             ["the hindu"],
        "The Times of India":    ["times of india"],
        "Hindustan Times":       ["hindustan times"],
        "The Indian Express":    ["indian express"],
        "The New Indian Express": ["new indian express"],
        "The Tribune":           ["the tribune"],
        "The Statesman":         ["the statesman"],
        "The Telegraph":         ["the telegraph", "telegraph india"],
        "The Economic Times":    ["economic times"],
    }

    match_pairs = []  # list of (lowercase_keyword, original_pub_name)

    for pub in publications:
        pub_lower = pub.lower().strip()
        match_pairs.append((pub_lower, pub))

        # Add aliases if available
        if pub in known_aliases:
            for alias in known_aliases[pub]:
                match_pairs.append((alias.lower().strip(), pub))

    return match_pairs


def is_priority(agency, match_pairs):
    """
    Check if the given agency name matches any priority publication.
    Uses case-insensitive substring matching in both directions:
      - priority keyword is found in the agency name, OR
      - agency name is found in the priority keyword
    Special care is taken to avoid false positives on short keywords.
    """
    agency_lower = agency.lower().strip()
    if not agency_lower:
        return False, None

    # Short keywords that need exact or near-exact matching to avoid false positives
    # e.g. "mint" should not match "BigMint", "pti" should not match "Egyptian..."
    short_exact = {"pti", "ians", "ani", "mint", "digit", "scroll", "the ken"}

    for keyword, pub_name in match_pairs:
        if keyword in short_exact:
            # For short keywords: match only if the agency IS the keyword,
            # or starts/ends with it as a word boundary
            if agency_lower == keyword:
                return True, pub_name
            # Check word-boundary matches: "Mint" matches "Mint", "livemint.com"
            # but not "BigMint" or "SugerMint"
            tokens = agency_lower.replace(".", " ").replace("-", " ").replace(",", " ").split()
            if keyword in tokens:
                return True, pub_name
            # Also check if agency starts with keyword (e.g., "digit.in")
            if agency_lower.startswith(keyword + ".") or agency_lower.startswith(keyword + " "):
                return True, pub_name
        else:
            # For longer keywords: substring match
            if keyword in agency_lower or agency_lower in keyword:
                return True, pub_name

    return False, None


def filter_csv(input_csv, priority_xlsx, output_csv, priority_output_csv):
    """
    Read the merged CSV, match each row's Agency against the priority media list,
    and write two output files:
      1. Non-priority articles (filtered_non_priority.csv)
      2. Priority-only articles (filtered_priority_only.csv)
    """
    # Load priority list
    publications = load_priority_publications(priority_xlsx)
    match_pairs = build_match_keywords(publications)

    print(f"\nReading input CSV: {input_csv}")

    total_rows = 0
    priority_count = 0
    non_priority_count = 0
    matched_pubs = {}  # track which priority pubs were matched and how many times

    with open(input_csv, "r", encoding="utf-8-sig", errors="replace") as infile, \
         open(output_csv, "w", encoding="utf-8", newline="") as out_non, \
         open(priority_output_csv, "w", encoding="utf-8", newline="") as out_pri:

        reader = csv.reader(infile)
        header = next(reader)

        writer_non = csv.writer(out_non)
        writer_pri = csv.writer(out_pri)
        writer_non.writerow(header)
        writer_pri.writerow(header)

        # Find the Agency column index
        try:
            agency_idx = header.index("Agency")
        except ValueError:
            print("ERROR: 'Agency' column not found in CSV header!")
            print(f"Available columns: {header}")
            return

        for row in reader:
            total_rows += 1
            agency = row[agency_idx] if agency_idx < len(row) else ""

            matched, pub_name = is_priority(agency, match_pairs)
            if matched:
                writer_pri.writerow(row)
                priority_count += 1
                matched_pubs[pub_name] = matched_pubs.get(pub_name, 0) + 1
            else:
                writer_non.writerow(row)
                non_priority_count += 1

    # ─── Summary ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("FILTERING COMPLETE")
    print("=" * 60)
    print(f"Total articles processed:     {total_rows}")
    print(f"Priority media articles:      {priority_count}")
    print(f"Non-priority media articles:  {non_priority_count}")
    print(f"\nPriority articles saved to:     {priority_output_csv}")
    print(f"Non-priority articles saved to: {output_csv}")

    if matched_pubs:
        print("\n--- Priority Media Matches Breakdown ---")
        for pub, count in sorted(matched_pubs.items(), key=lambda x: -x[1]):
            print(f"  {pub:<35} {count:>5} articles")


if __name__ == "__main__":
    filter_csv(INPUT_CSV, PRIORITY_LIST_XLSX, OUTPUT_CSV, PRIORITY_OUTPUT_CSV)
