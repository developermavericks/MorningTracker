import os
import csv
import sys

# Increase CSV field size limit to handle large text blocks in 'Full Body'
max_limit = sys.maxsize
while True:
    try:
        csv.field_size_limit(max_limit)
        break
    except OverflowError:
        max_limit = int(max_limit / 10)

def merge_csv_files(input_files, output_file):
    print("Starting the merging process...")
    
    header_written = False
    total_rows = 0
    
    # Open output file
    try:
        with open(output_file, mode='w', encoding='utf-8', newline='') as outfile:
            writer = None
            
            for file_path in input_files:
                if not os.path.exists(file_path):
                    print(f"Warning: File {file_path} not found. Skipping.")
                    continue
                
                print(f"Processing: {os.path.basename(file_path)}...")
                
                # Using utf-8-sig to automatically handle BOM if present
                with open(file_path, mode='r', encoding='utf-8-sig', errors='replace') as infile:
                    reader = csv.reader(infile)
                    
                    # Read header
                    try:
                        header = next(reader)
                    except StopIteration:
                        print(f"Warning: File {file_path} is empty. Skipping.")
                        continue
                    
                    # Initialize writer with the header from the first file
                    if not header_written:
                        writer = csv.writer(outfile)
                        writer.writerow(header)
                        header_written = True
                        print(f"Header written: {header}")
                    
                    # Write rows
                    rows_written = 0
                    for row in reader:
                        writer.writerow(row)
                        rows_written += 1
                    
                    total_rows += rows_written
                    print(f"Successfully appended {rows_written} rows from {os.path.basename(file_path)}.")
                    
        print("\nMerging complete!")
        print(f"Total rows successfully written (excluding headers): {total_rows}")
        print(f"Merged output saved to: {output_file}")
        
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    # List of the three files to merge
    input_files = [
        "Nexus_Report_Google3_2026-07-08.csv",
        "Nexus_Report_google_2026-07-08.csv",
        "Nexus_Report_google_2_2026-07-08.csv"
    ]
    
    output_file = "final.csv"
    
    merge_csv_files(input_files, output_file)
