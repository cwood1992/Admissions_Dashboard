#!/usr/bin/env python3
"""
CCS Export Processor for Admissions Dashboard
Reads raw STARS CCS exports and generates summary CSV for dashboard.

Usage:
    python process_ccs.py [input_folder] [output_file]
    
Defaults:
    input_folder: ./CCS_Raw/
    output_file: ./summary.csv

Drop raw CCS exports (CCS-N560.csv, etc.) into input folder and run.
"""

import pandas as pd
import os
import sys
import re
from pathlib import Path
from datetime import datetime

# Configuration
HEADER_ROWS_TO_SKIP = 6  # STARS exports have 6 metadata rows before column headers
START_STATUSES = {'Active', 'Drop', 'Grad'}  # Statuses that count as "started"

def extract_program(cohort_name):
    """Extract program type from cohort name (NDT560 -> NDT, UDT559 -> UDT, NDT560NC -> NDT-NC)"""
    if not cohort_name or pd.isna(cohort_name):
        return 'Unknown'
    
    cohort_name = str(cohort_name).strip().upper()
    
    if 'NC' in cohort_name:
        if 'NDT' in cohort_name:
            return 'NDT-NC'
        elif 'UDT' in cohort_name:
            return 'UDT-NC'
    elif 'NDT' in cohort_name:
        return 'NDT'
    elif 'UDT' in cohort_name:
        return 'UDT'
    
    return 'Other'

def extract_cohort_number(cohort_name):
    """Extract numeric portion for sorting (NDT560 -> 560)"""
    if not cohort_name or pd.isna(cohort_name):
        return 0
    match = re.search(r'(\d+)', str(cohort_name))
    return int(match.group(1)) if match else 0

def process_single_file(filepath):
    """Process a single CCS export file and return records."""
    try:
        # Read CSV, skipping STARS metadata header rows
        df = pd.read_csv(filepath, skiprows=HEADER_ROWS_TO_SKIP, dtype=str)
        
        # Normalize column names (strip whitespace, handle variations)
        df.columns = df.columns.str.strip()
        
        # Required columns
        required_cols = ['Lead Rep', 'CCS Cohort', 'CCS Status', 'Enroll Type']
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            print(f"  WARNING: Missing columns {missing} in {filepath.name}")
            return None
        
        # Clean up data
        df['Lead Rep'] = df['Lead Rep'].fillna('Unassigned').str.strip()
        df['CCS Cohort'] = df['CCS Cohort'].fillna('').str.strip()
        df['CCS Status'] = df['CCS Status'].fillna('').str.strip()
        df['Enroll Type'] = df['Enroll Type'].fillna('NEW').str.strip().str.upper()
        
        # Filter out empty cohorts
        df = df[df['CCS Cohort'] != '']
        
        return df
        
    except Exception as e:
        print(f"  ERROR processing {filepath.name}: {e}")
        return None

def aggregate_data(all_records):
    """Aggregate records into summary by Rep x Cohort."""
    
    summary = []
    
    # Group by Cohort and Rep
    grouped = all_records.groupby(['CCS Cohort', 'Lead Rep'])
    
    for (cohort, rep), group in grouped:
        program = extract_program(cohort)
        
        # Count enrollments (all records)
        enrollments = len(group)
        
        # Count by enrollment type
        enroll_types = group['Enroll Type'].value_counts()
        new_count = enroll_types.get('NEW', 0)
        transfer_count = enroll_types.get('TRANSFER', 0)
        reenroll_count = enroll_types.get('REENROLL', 0)
    
         # Count starts (Active, Drop, Grad, less reenrollments)
        starts = len(group[group['CCS Status'].isin(START_STATUSES) & (group['Enroll Type'] != 'REENROLL')])
       
        # Start rate
        start_rate = round(starts / enrollments * 100, 1) if enrollments > 0 else 0
        
        summary.append({
            'Cohort': cohort,
            'Program': program,
            'Rep': rep,
            'Enrollments': enrollments,
            'Starts': starts,
            'StartRate': start_rate,
            'New': new_count,
            'Transfer': transfer_count,
            'Reenroll': reenroll_count
        })
    
    return pd.DataFrame(summary)

def main():
    # Parse arguments
    input_folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('./CCS_Raw/')
    output_file = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('./summary.csv')
    
    print(f"CCS Export Processor")
    print(f"=" * 50)
    print(f"Input folder: {input_folder.absolute()}")
    print(f"Output file:  {output_file.absolute()}")
    print()
    
    # Check input folder exists
    if not input_folder.exists():
        print(f"Creating input folder: {input_folder}")
        input_folder.mkdir(parents=True)
        print(f"Drop CCS export files into {input_folder} and run again.")
        return
    
    # Find all CSV files
    csv_files = list(input_folder.glob('*.csv'))
    
    if not csv_files:
        print(f"No CSV files found in {input_folder}")
        print(f"Drop CCS export files (e.g., CCS-N560.csv) into the folder and run again.")
        return
    
    print(f"Found {len(csv_files)} CSV file(s):")
    
    # Process each file
    all_records = []
    for filepath in sorted(csv_files):
        print(f"  Processing {filepath.name}...", end=' ')
        df = process_single_file(filepath)
        if df is not None:
            all_records.append(df)
            print(f"({len(df)} records)")
        else:
            print("SKIPPED")
    
    if not all_records:
        print("\nNo valid records found.")
        return
    
    # Combine all records
    combined = pd.concat(all_records, ignore_index=True)
    
    # Remove duplicates (same student in same cohort from multiple exports)
    if 'ID' in combined.columns:
        before = len(combined)
        combined = combined.drop_duplicates(subset=['ID', 'CCS Cohort'], keep='last')
        dupes = before - len(combined)
        if dupes > 0:
            print(f"\nRemoved {dupes} duplicate records")
    
    print(f"\nTotal records: {len(combined)}")
    
    # Aggregate
    summary = aggregate_data(combined)
    
    # Sort by cohort number (descending) then rep
    summary['_sort'] = summary['Cohort'].apply(extract_cohort_number)
    summary = summary.sort_values(['Program', '_sort', 'Rep'], ascending=[True, False, True])
    summary = summary.drop('_sort', axis=1)
    
    # Save
    summary.to_csv(output_file, index=False)
    print(f"\nSummary saved to {output_file}")
    print(f"  {len(summary)} rows (Rep x Cohort combinations)")
    
    # Print preview
    print(f"\nPreview:")
    print(summary.to_string(index=False, max_rows=20))
    
    # Print totals by cohort
    print(f"\n" + "=" * 50)
    print("Totals by Cohort:")
    totals = summary.groupby('Cohort').agg({
        'Enrollments': 'sum',
        'Starts': 'sum'
    }).reset_index()
    totals['StartRate'] = (totals['Starts'] / totals['Enrollments'] * 100).round(1)
    print(totals.to_string(index=False))

if __name__ == '__main__':
    main()
