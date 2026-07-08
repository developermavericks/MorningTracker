import csv
import os
import sys

# Increase CSV field size limit
max_limit = sys.maxsize
while True:
    try:
        csv.field_size_limit(max_limit)
        break
    except OverflowError:
        max_limit = int(max_limit // 10)

def segregate_by_sector(input_csv, output_dir):
    print(f"Reading matched articles from: {input_csv}")
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    sector_writers = {}
    sector_files = {}
    
    try:
        with open(input_csv, 'r', encoding='utf-8-sig', errors='replace') as infile:
            reader = csv.reader(infile)
            header = next(reader)
            
            try:
                sector_idx = header.index('Sector')
            except ValueError:
                print("ERROR: 'Sector' column not found in the CSV!")
                return
                
            for row in reader:
                if sector_idx >= len(row):
                    continue
                    
                sector = row[sector_idx].strip()
                if not sector:
                    sector = "Unknown_Sector"
                    
                # Clean sector name for valid filename
                safe_sector_name = "".join([c if c.isalnum() or c in " _-" else "_" for c in sector]).strip()
                
                if safe_sector_name not in sector_writers:
                    # Create new file and writer for this sector
                    filename = os.path.join(output_dir, f"Sector_{safe_sector_name}.csv")
                    f = open(filename, 'w', encoding='utf-8', newline='')
                    writer = csv.writer(f)
                    writer.writerow(header)
                    
                    sector_writers[safe_sector_name] = writer
                    sector_files[safe_sector_name] = f
                
                sector_writers[safe_sector_name].writerow(row)
                
    finally:
        # Close all opened files
        for f in sector_files.values():
            f.close()
            
    print("\nSegregation Complete! Files created:")
    for sector, f in sector_files.items():
        print(f"  - {f.name}")

if __name__ == "__main__":
    INPUT_CSV = r"E:\MAVERICKS\Heavy_automation_pooja_codefiles\keyword_matched_articles.csv"
    OUTPUT_DIR = r"E:\MAVERICKS\Heavy_automation_pooja_codefiles\Sector_Segregated"
    
    segregate_by_sector(INPUT_CSV, OUTPUT_DIR)
