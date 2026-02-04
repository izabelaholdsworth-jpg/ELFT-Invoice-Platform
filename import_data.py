import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch
from datetime import datetime
import sys
import os
import numpy as np
from config import DB_CONFIG

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

def clean_column_name(col):
    """Convert Excel column name to database column name"""
    return col.strip().lower().replace(' ', '_').replace('(', '').replace(')', '').replace('.', '_').replace('/', '_')

def import_ap_transactions():
    print("\n" + "="*60)
    print("IMPORTING AP TRANSACTIONS")
    print("="*60)
    
    # Updated path to match user's actual workspace
    file_path = os.path.join(os.getcwd(), "mental_health_trust_data_categorized_FINAL.xlsx")
    
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    # Read Excel
    print(f"Reading file: {file_path}")
    df = pd.read_excel(file_path)
    print(f"✓ Loaded {len(df):,} rows")
    
    # Clean column names
    df.columns = [clean_column_name(col) for col in df.columns]
    
    # Map to database columns
    column_mapping = {
        'subjective_name': 'subjective_name',
        'amount_£': 'amount_gbp',
        'month': 'month',
        'date': 'transaction_date',
        'party': 'party',
        'source_transaction': 'source_transaction',
        'description': 'description',
        'source': 'source',
        'unit_price': 'unit_price',
        'quantity': 'quantity',
        'uom': 'uom',
        'financial_year': 'financial_year',
        'period': 'period',
        'month_1': 'month_1',
        'ward': 'ward',
        'directorate': 'directorate',
        'department': 'department',
        'service': 'service',
        'cost_centre_description': 'cost_centre_description',
        'category_1': 'category_1',
        'category_2': 'category_2',
        'account_code_name_level_5': 'account_code_name_level_5',
        'account_code_name_level_6': 'account_code_name_level_6',
        'category': 'category',
        'subjective_code_description': 'subjective_code_description',
        'analysis_one_code_description': 'analysis_one_code_description',
        'spend_category': 'spend_category',
        'final_category': 'final_category',
        'sub_category': 'sub_category',
        'site_type': 'site_type',
        'high': 'high',
        'coding': 'coding',
        'non_po_flag': 'non_po_flag'
    }
    
    # Rename columns
    df.rename(columns=column_mapping, inplace=True)
    
    # Convert dates
    if 'transaction_date' in df.columns:
        df['transaction_date'] = pd.to_datetime(df['transaction_date'], errors='coerce')
    if 'period' in df.columns:
        df['period'] = pd.to_datetime(df['period'], errors='coerce')
    
    # Handle NaN
    df = df.where(pd.notnull(df), None)
    
    # Get columns that exist in both dataframe and our mapping
    columns = [col for col in df.columns if col in column_mapping.values()]
    
    # Prepare insert
    conn = get_db_connection()
    cursor = conn.cursor()
    
    insert_sql = f"""
        INSERT INTO ap_transactions ({', '.join(columns)})
        VALUES ({', '.join(['%s'] * len(columns))})
    """
    
    # Prepare data
    data = [tuple(row[col] for col in columns) for _, row in df.iterrows()]
    
    # Insert in batches
    print(f"Inserting {len(data):,} transactions...")
    execute_batch(cursor, insert_sql, data, page_size=1000)
    conn.commit()
    
    # Statistics
    cursor.execute("""
        SELECT 
            COUNT(*) as transactions,
            COUNT(DISTINCT party) as suppliers,
            SUM(amount_gbp) as total_spend,
            SUM(CASE WHEN non_po_flag = 'Y' THEN amount_gbp ELSE 0 END) as non_po_spend
        FROM ap_transactions
    """)
    stats = cursor.fetchone()
    
    print(f"\n✓ Import Complete:")
    print(f"  Transactions: {stats[0]:,}")
    print(f"  Suppliers: {stats[1]:,}")
    print(f"  Total Spend: £{stats[2]:,.2f}")
    if stats[2] > 0:
        print(f"  Non-PO Spend: £{stats[3]:,.2f} ({stats[3]/stats[2]*100:.1f}%)")
    else:
        print(f"  Non-PO Spend: £{stats[3]:,.2f}")
    
    cursor.close()
    conn.close()

def import_contracts():
    print("\n" + "="*60)
    print("IMPORTING CONTRACTS")
    print("="*60)

    # Updated path to match user's actual workspace
    file_path = os.path.join(os.getcwd(), "Contracts register ELFT - Steering Group KPIs.xlsx")

    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    # Read Sheet1 directly without header first to find the correct header row
    print(f"\nProcessing: Sheet1")

    # Read first 50 rows to find header
    df_header_search = pd.read_excel(file_path, sheet_name='Sheet1', header=None, nrows=50)

    header_row = None
    for i in range(len(df_header_search)):
        row_values = [str(val).lower() for val in df_header_search.iloc[i]]
        row_str = ' '.join(row_values)
        if 'supplier' in row_str and ('contract' in row_str or 'budget' in row_str):
            header_row = i
            print(f"  Found header at row {header_row}")
            break

    if header_row is None:
        print("✗ Could not find header row in Sheet1")
        return

    # Now read the full sheet with the correct header
    df = pd.read_excel(file_path, sheet_name='Sheet1', header=header_row)
    print(f"  Loaded {len(df)} rows from Sheet1")
    
    # Print original column names for debugging
    print(f"\n  Original columns (first 20): {list(df.columns)[:20]}")
    print(f"  Total columns: {len(df.columns)}")

    # Read specific columns by position (0-indexed)
    # Column E (index 4) = Supplier
    # Column G (index 6) = Start Date
    # Column H (index 7) = End Date
    # Column AR (index 43) = 24/25 Budget
    # Column AS (index 44) = 25/26 Budget

    # Create new dataframe with specific columns
    df_mapped = pd.DataFrame()

    if len(df.columns) > 4:
        df_mapped['supplier'] = df.iloc[:, 4]  # Column E
    if len(df.columns) > 6:
        df_mapped['start_date'] = df.iloc[:, 6]  # Column G
    if len(df.columns) > 7:
        df_mapped['end_date'] = df.iloc[:, 7]  # Column H
    if len(df.columns) > 43:
        df_mapped['budget_2425'] = df.iloc[:, 43]  # Column AR
    if len(df.columns) > 44:
        df_mapped['budget_2526'] = df.iloc[:, 44]  # Column AS

    # Try to find other useful columns by name
    df.columns = [clean_column_name(col) for col in df.columns]

    # Map additional columns if they exist
    additional_mapping = {
        'service_rag': 'service_rag',
        'subcontract_reference': 'subcontract_reference',
        'tier': 'tier',
        'contract_name': 'contract_name',
        'documents_rag': 'documents_rag',
        'overdue': 'overdue',
        'category': 'category',
        'estimated_total_contract_value_exc_vat': 'estimated_total_contract_value',
        'estimated_total_contract_value': 'estimated_total_contract_value',
        'elft_contract_lead': 'elft_contract_lead',
        'contract_lead': 'elft_contract_lead'
    }

    for old_col, new_col in additional_mapping.items():
        if old_col in df.columns and new_col not in df_mapped.columns:
            df_mapped[new_col] = df[old_col]

    df = df_mapped
    print(f"  Mapped columns: {list(df.columns)}")
    
    # Convert dates and clean immediately
    for col in ['start_date', 'end_date']:
        if col in df.columns:
            print(f"  Converting {col} to datetime...")
            df[col] = pd.to_datetime(df[col], errors='coerce')
            df[col] = df[col].apply(lambda x: None if pd.isna(x) else x)
            print(f"    Sample values: {df[col].head(3).tolist()}")

    # Clean currency columns manually
    currency_cols = ['estimated_total_contract_value', 'budget_2425', 'budget_2526']
    for col in currency_cols:
        if col in df.columns:
            print(f"  Converting {col} to numeric...")
            # Handle various formats
            df[col] = df[col].astype(str).str.replace('£', '', regex=False).str.replace(',', '', regex=False).str.replace(' ', '', regex=False).str.strip()
            df[col] = pd.to_numeric(df[col], errors='coerce')
            print(f"    Sample values: {df[col].head(3).tolist()}")

    # Handle remaining NaN/NaT
    df = df.astype(object)
    df = df.where(pd.notnull(df), None)
    df.replace({np.nan: None, pd.NaT: None}, inplace=True)
    
    # Filter valid rows
    df = df[df['supplier'].notna()]
    
    # Get columns
    columns = [col for col in df.columns if col in column_mapping.values()]
    
    # Insert
    conn = get_db_connection()
    cursor = conn.cursor()
    
    insert_sql = f"""
        INSERT INTO contracts ({', '.join(columns)})
        VALUES ({', '.join(['%s'] * len(columns))})
    """
    
    # Manual data preparation
    data = []
    for _, row in df.iterrows():
        row_data = []
        for col in columns:
            val = row[col]
            # Robust check for empty/NaN values
            if pd.isna(val) or val == '' or str(val).lower() == 'nan' or str(val).lower() == 'nat':
                val = None
            row_data.append(val)
        data.append(tuple(row_data))
    
    print(f"Inserting {len(data):,} contracts...")
    execute_batch(cursor, insert_sql, data, page_size=100)
    conn.commit()
    
    # Statistics
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE end_date > CURRENT_DATE) as active,
            COUNT(*) FILTER (WHERE end_date < CURRENT_DATE) as expired,
            SUM(estimated_total_contract_value) as total_value
        FROM contracts
    """)
    stats = cursor.fetchone()
    
    print(f"\n✓ Import Complete:")
    print(f"  Total Contracts: {stats[0]:,}")
    print(f"  Active: {stats[1]:,}")
    print(f"  Expired: {stats[2]:,}")
    if stats[3]:
        print(f"  Total Value: £{stats[3]:,.2f}")
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    try:
        # AP Transactions already imported successfully
        # import_ap_transactions()
        import_contracts()
        print("\n" + "="*60)
        print("✓ ALL IMPORTS COMPLETE")
        print("="*60)
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
