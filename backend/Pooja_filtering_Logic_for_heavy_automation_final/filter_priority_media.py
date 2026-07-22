import os
import csv
import sys
import re
import openpyxl

# ─── Robust CSV field size limit (handles large 'Full Body' blocks) ──────────
_max_limit = sys.maxsize
while True:
    try:
        csv.field_size_limit(_max_limit)
        break
    except OverflowError:
        _max_limit = int(_max_limit // 10)

# ─── Configuration ───────────────────────────────────────────────────────────
INPUT_CSV = r"E:\MAVERICKS\Heavy_automation_pooja_codefiles\final.csv"
PRIORITY_LIST_XLSX = r"E:\MAVERICKS\Heavy_automation_pooja_codefiles\[Internal] Google Online Priority Media List 2026.xlsx"
OUTPUT_CSV = r"E:\MAVERICKS\Heavy_automation_pooja_codefiles\filtered_non_priority.csv"
PRIORITY_OUTPUT_CSV = r"E:\MAVERICKS\Heavy_automation_pooja_codefiles\filtered_priority_only.csv"

AGENCY_COLUMN = "Agency"

# Known aliases: priority list name -> additional CSV agency patterns.
# Add short/abbreviated forms here explicitly if they appear in your data;
# the matcher no longer guesses them via reverse substring.
KNOWN_ALIASES = {
    "PTI":                    ["pti"],
    "IANS":                   ["ians"],
    "ANI":                    ["ani", "ani news", "aninews"],
    "Reuters India":          ["reuters"],
    "NDTV":                   ["ndtv"],
    "BloombergQuint":         ["ndtv profit", "ndtvprofit", "bloombergquint"],
    "NDTV Gadgets360":        ["gadgets 360", "gadgets360"],
    "Gadgets Now":            ["gadgets now", "gadgetsnow"],
    "Moneycontrol":           ["moneycontrol"],
    "91Mobiles":              ["91mobiles"],
    "Analytics India":        ["analytics india", "analyticsindia", "aim media house", "aimmediahouse"],
    "Digit":                  ["digit.in", "digit"],
    "YourStory":              ["yourstory"],
    "India Times":            ["indiatimes"],
    "The Print":              ["the print", "theprint"],
    "TechCircle":             ["techcircle"],
    "VCCircle":               ["vccircle"],
    "Scroll.in":              ["scroll.in", "scroll"],
    "Aaj Tak":                ["aaj tak", "aajtak"],
    "News18":                 ["news18"],
    "Mint":                   ["mint", "livemint"],
    "The Financial Express":  ["financial express", "financialexpress"],
    "Business Standard":      ["business standard", "businessstandard"],
    "Outlook India":          ["outlook india", "outlookindia"],
    "Outlook Business":       ["outlook business", "outlookbusiness"],
    "BW BusinessWorld":       ["bw businessworld", "bwbusinessworld", "bw business", "bwbusiness", "businessworld"],
    "Inc42":                  ["inc42"],
    "Forbes India":           ["forbes india", "forbesindia"],
    "Fortune India":          ["fortune india", "fortuneindia"],
    "Business Today":         ["business today", "businesstoday"],
    "Business India":         ["business india", "businessindia"],
    "The Ken":                ["the ken", "theken"],
    "The Quint":              ["the quint", "thequint"],
    "The Morning Context":    ["the morning context", "themorningcontext"],
    "Deccan Herald":          ["deccan herald", "deccanherald"],
    "Deccan Chronicle":       ["deccan chronicle", "deccanchronicle"],
    "India Today":            ["india today", "indiatoday"],
    "ET BrandEquity":         ["et brandequity", "etbrandequity", "brandequity"],
    "afaqs!":                 ["afaqs"],
    "Exchange4Media":         ["exchange4media"],
    "Medianama":              ["medianama"],
    "Amar Ujala":             ["amar ujala", "amarujala"],
    "Dainik Bhaskar":         ["dainik bhaskar", "dainikbhaskar"],
    "Bhaskar Hindi":          ["bhaskar hindi", "bhaskarhindi"],
    "Bhaskar Live":           ["bhaskar live", "bhaskarlive"],
    "Dainik Jagran":          ["dainik jagran", "dainikjagran", "daily jagran", "dailyjagran", "jagran"],
    "Navbharat Times":        ["navbharat times", "navbharattimes"],
    "DT Next":                ["dt next", "dtnext"],
    "Mumbai Mirror":          ["mumbai mirror", "mumbaimirror"],
    "The Hindu":              ["the hindu", "thehindu"],
    "The Times of India":     ["times of india", "timesofindia"],
    "Hindustan Times":        ["hindustan times", "hindustantimes"],
    "The Indian Express":     ["the indian express", "indian express", "indianexpress"],
    "The New Indian Express": ["new indian express", "newindianexpress"],
    "The Tribune":            ["the tribune", "thetribune"],
    "The Statesman":          ["the statesman", "thestatesman"],
    "The Telegraph":          ["the telegraph", "thetelegraph", "telegraph india", "telegraphindia"],
    "The Economic Times":     ["economic times", "economictimes"],
}

# Skip-list: rows in the Excel whose name equals one of these are ignored.
_SKIP_NAMES = {"", "name", "publication", "publications", "media", "s.no", "sno", "serial"}


def load_priority_publications(xlsx_path):
    """Read the priority media list. Returns a list of cleaned publication names."""
    if not os.path.isfile(xlsx_path):
        raise FileNotFoundError(f"Priority list not found: {xlsx_path}")

    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb.active

    def clean(name):
        # "BloombergQuint\n(now NDTV Profit)" -> "BloombergQuint"
        return str(name).strip().split("\n")[0].strip()

    strict, lenient = [], []
    for row in ws.iter_rows(min_row=2, values_only=True):
        cells = list(row) + [None, None]
        serial, name = cells[0], cells[1]
        if not name:
            continue
        cname = clean(name)
        if cname.lower() in _SKIP_NAMES or len(cname) > 120:
            continue
        lenient.append(cname)
        if isinstance(serial, (int, float)):
            strict.append(cname)

    wb.close()

    # Prefer the strict (serial-numbered) rows; fall back if the layout differs.
    publications = strict if strict else lenient
    if strict and len(lenient) > len(strict):
        print(f"NOTE: {len(lenient) - len(strict)} row(s) had no numeric serial and were skipped.")
    if not strict and lenient:
        print("WARNING: no numeric serial column detected; loaded names leniently from column B.")
    if not publications:
        raise ValueError("No publications could be read from the Excel file. "
                         "Check that names are in column B starting at row 2.")

    # De-duplicate, preserve order
    seen, unique = set(), []
    for p in publications:
        if p.lower() not in seen:
            seen.add(p.lower())
            unique.append(p)

    print(f"Loaded {len(unique)} priority publications from Excel:")
    for pub in unique:
        print(f"  • {pub}")
    return unique


def _boundary_regex(pattern):
    """
    Compile a word-boundary-aware regex for a lowercase pattern.
    Boundary is only enforced on an edge that is alphanumeric, so patterns
    like 'afaqs!' or 'scroll.in' still match correctly at string ends.
    """
    esc = re.escape(pattern)
    left = r"(?<!\w)" if pattern[:1].isalnum() else r""
    right = r"(?!\w)" if pattern[-1:].isalnum() else r""
    return re.compile(left + esc + right)


def build_matchers(publications):
    """
    Build a list of (compiled_regex, pattern_str, pub_name), sorted so the
    LONGEST pattern is tested first. Longest-first is what makes specific
    names ('ndtv profit', 'new indian express') win over generic prefixes.
    """
    seen = set()
    pairs = []  # (pattern_str, pub_name)

    def add(pattern, pub):
        p = pattern.lower().strip()
        if p and p not in seen:
            seen.add(p)
            pairs.append((p, pub))

    for pub in publications:
        add(pub, pub)                       # the publication's own name
        for alias in KNOWN_ALIASES.get(pub, []):
            add(alias, pub)

    pairs.sort(key=lambda pp: len(pp[0]), reverse=True)
    return [(_boundary_regex(p), p, pub) for p, pub in pairs]


def match_agency(agency, matchers):
    """
    Return (pub_name, matched_pattern) for the first (longest) pattern that
    matches the agency as a whole word, else (None, None). Deterministic.
    """
    if not agency:
        return None, None
    a = agency.lower().strip()
    if not a:
        return None, None
    for rx, pattern, pub in matchers:
        if rx.search(a):
            return pub, pattern
    return None, None


def filter_csv(input_csv, priority_xlsx, output_csv, priority_output_csv):
    if not os.path.isfile(input_csv):
        raise FileNotFoundError(f"Input CSV not found: {input_csv}")

    publications = load_priority_publications(priority_xlsx)
    matchers = build_matchers(publications)

    print(f"\nReading input CSV: {input_csv}")

    total = priority_count = non_priority = skipped_no_agency = 0
    matched_pubs = {}
    unmatched_samples = {}  # distinct unmatched agency -> count (for tuning)

    with open(input_csv, "r", encoding="utf-8-sig", errors="replace", newline="") as infile, \
         open(output_csv, "w", encoding="utf-8", newline="") as out_non, \
         open(priority_output_csv, "w", encoding="utf-8", newline="") as out_pri:

        reader = csv.reader(infile)
        try:
            header = next(reader)
        except StopIteration:
            print("ERROR: input CSV is empty.")
            return

        try:
            agency_idx = header.index(AGENCY_COLUMN)
        except ValueError:
            print(f"ERROR: '{AGENCY_COLUMN}' column not found in CSV header!")
            print(f"Available columns: {header}")
            return

        writer_non = csv.writer(out_non)
        writer_pri = csv.writer(out_pri)
        writer_non.writerow(header)
        writer_pri.writerow(header)

        for row in reader:
            total += 1
            agency = row[agency_idx] if agency_idx < len(row) else ""
            if not agency.strip():
                skipped_no_agency += 1

            pub_name, _ = match_agency(agency, matchers)
            if pub_name:
                writer_pri.writerow(row)
                priority_count += 1
                matched_pubs[pub_name] = matched_pubs.get(pub_name, 0) + 1
            else:
                writer_non.writerow(row)
                non_priority += 1
                key = agency.strip()
                if key:
                    unmatched_samples[key] = unmatched_samples.get(key, 0) + 1

    # ─── Summary ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("FILTERING COMPLETE")
    print("=" * 60)
    print(f"Total articles processed:     {total}")
    print(f"Priority media articles:      {priority_count}")
    print(f"Non-priority media articles:  {non_priority}")
    if skipped_no_agency:
        print(f"Rows with blank Agency:       {skipped_no_agency}")
    print(f"\nPriority articles saved to:     {priority_output_csv}")
    print(f"Non-priority articles saved to: {output_csv}")

    if matched_pubs:
        print("\n--- Priority Media Matches Breakdown ---")
        for pub, count in sorted(matched_pubs.items(), key=lambda x: -x[1]):
            print(f"  {pub:<35} {count:>5} articles")

    # Show the most common UNMATCHED agencies so you can spot missing aliases.
    if unmatched_samples:
        print("\n--- Top 25 unmatched agencies (check for missed publications) ---")
        for name, count in sorted(unmatched_samples.items(), key=lambda x: -x[1])[:25]:
            print(f"  {name:<40} {count:>5}")


# ─── Backward-compatibility shims for backend/scraper/tasks.py ───────────────
# Older callers import build_match_keywords / is_priority. Keep them working:
#   match_pairs = build_match_keywords(pubs)       # returns new matcher list
#   matched, pub = is_priority(agency, match_pairs) # (bool, name) as before
def build_match_keywords(publications):
    """Legacy name for build_matchers(). Returns the new compiled-matcher list."""
    return build_matchers(publications)


def is_priority(agency, match_pairs):
    """Legacy name for match_agency(). Returns (matched_bool, pub_name)."""
    pub_name, _ = match_agency(agency, match_pairs)
    return (pub_name is not None), pub_name


if __name__ == "__main__":
    filter_csv(INPUT_CSV, PRIORITY_LIST_XLSX, OUTPUT_CSV, PRIORITY_OUTPUT_CSV)
