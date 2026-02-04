from flask import Flask, render_template, jsonify, request
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from anthropic import Anthropic
from decimal import Decimal
from datetime import date, datetime
import json
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'contract_management',
    'user': 'contract_admin',
    'password': 'SecurePass2026!'
}

# Initialize Anthropic client
try:
    anthropic_client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY', ''))
except:
    anthropic_client = None

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)

def serialize_value(val):
    """Convert database values to JSON-serializable format"""
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, (date, datetime)):
        return val.isoformat()
    return val

# ROUTES
@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/contracts')
def contracts_page():
    return render_template('contracts.html')

@app.route('/ai')
def ai_page():
    return render_template('ai_chat.html')

# API ENDPOINTS

@app.route('/api/dashboard/kpis')
def get_kpis():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Exclude August 2024 and November 2024 (extreme values)
    exclude_filter = "WHERE month NOT IN ('2024-08', '2024-11', 'Aug-24', 'Nov-24', 'August 2024', 'November 2024')"

    # Total spend
    cursor.execute(f"SELECT COALESCE(SUM(amount_gbp), 0) FROM ap_transactions {exclude_filter}")
    result = cursor.fetchone()
    total_spend = float(result['coalesce']) if result else 0

    # Active contracts
    cursor.execute("SELECT COUNT(*) FROM contracts WHERE end_date > CURRENT_DATE")
    active_contracts = cursor.fetchone()['count']

    # Non-PO percentage (hardcoded as requested)
    non_po_pct = 56.37
    
    # Expiring contracts (next 90 days)
    cursor.execute("""
        SELECT COUNT(*) 
        FROM contracts 
        WHERE end_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '90 days'
    """)
    expiring = cursor.fetchone()['count']
    
    # Unique suppliers
    cursor.execute(f"SELECT COUNT(DISTINCT party) FROM ap_transactions {exclude_filter}")
    suppliers = cursor.fetchone()['count']

    # Average transaction
    cursor.execute(f"SELECT COALESCE(AVG(amount_gbp), 0) FROM ap_transactions {exclude_filter}")
    result = cursor.fetchone()
    avg_transaction = float(result['coalesce']) if result else 0

    # Suppliers without contracts
    cursor.execute("SELECT COUNT(*) FROM vw_suppliers_without_contracts")
    no_contract_suppliers = cursor.fetchone()['count']

    # Top 20 concentration
    cursor.execute(f"""
        WITH supplier_totals AS (
            SELECT party, SUM(amount_gbp) as spend
            FROM ap_transactions
            {exclude_filter}
            GROUP BY party
            ORDER BY spend DESC
            LIMIT 20
        )
        SELECT
            COALESCE(
                ROUND(SUM(spend) / (SELECT SUM(amount_gbp) FROM ap_transactions {exclude_filter}) * 100, 1),
                0
            ) as pct
        FROM supplier_totals
    """)
    result = cursor.fetchone()
    concentration = float(result['pct'] or 0)
    
    cursor.close()
    conn.close()
    
    return jsonify({
        'total_spend': total_spend,
        'active_contracts': active_contracts,
        'non_po_percentage': non_po_pct,
        'expiring_contracts': expiring,
        'unique_suppliers': suppliers,
        'avg_transaction': avg_transaction,
        'no_contract_suppliers': no_contract_suppliers,
        'top_20_concentration': concentration
    })

@app.route('/api/dashboard/charts')
def get_chart_data():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Exclude August 2024 and November 2024 (extreme values)
    exclude_filter = "WHERE month NOT IN ('2024-08', '2024-11', 'Aug-24', 'Nov-24', 'August 2024', 'November 2024')"

    # Monthly trend
    cursor.execute(f"""
        SELECT month, total_spend, non_po_spend, po_spend, non_po_percentage
        FROM vw_monthly_dashboard
        {exclude_filter}
        ORDER BY month
    """)
    monthly = [dict(row) for row in cursor.fetchall()]
    for row in monthly:
        for key, val in row.items():
            row[key] = serialize_value(val)
    
    # Category spend (Top 10) - exclude extreme months from the view calculation
    cursor.execute(f"""
        SELECT
            final_category,
            SUM(amount_gbp) as total_spend,
            ROUND(
                SUM(CASE WHEN source = 'No PO' THEN amount_gbp ELSE 0 END) /
                NULLIF(SUM(amount_gbp), 0) * 100,
                2
            ) as non_po_percentage
        FROM ap_transactions
        {exclude_filter}
        GROUP BY final_category
        HAVING SUM(amount_gbp) > 0
        ORDER BY total_spend DESC
        LIMIT 10
    """)
    categories = [dict(row) for row in cursor.fetchall()]
    for row in categories:
        for key, val in row.items():
            row[key] = serialize_value(val)
    
    # Non-PO by directorate - calculate directly from ap_transactions (based on source)
    cursor.execute(f"""
        SELECT
            directorate,
            SUM(amount_gbp) as spend,
            ROUND(
                SUM(CASE WHEN source = 'No PO' THEN amount_gbp ELSE 0 END) /
                NULLIF(SUM(amount_gbp), 0) * 100,
                2
            ) as non_po_pct
        FROM ap_transactions
        {exclude_filter}
        AND directorate IS NOT NULL
        AND directorate != ''
        GROUP BY directorate
        HAVING SUM(amount_gbp) > 1000
        ORDER BY spend DESC
        LIMIT 10
    """)
    directorates = [dict(row) for row in cursor.fetchall()]
    for row in directorates:
        for key, val in row.items():
            row[key] = serialize_value(val)
    
    cursor.close()
    conn.close()
    
    return jsonify({
        'monthly_trend': monthly,
        'category_spend': categories,
        'directorate_spend': directorates
    })

@app.route('/api/contracts')
def get_contracts():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get status filter
        status_filter = request.args.get('status', 'all')
        search = request.args.get('search', '')
        
        # Base query
        query = "SELECT * FROM vw_contract_vs_invoiced WHERE 1=1"
        params = []
        
        # Apply filters
        if status_filter != 'all':
            query += " AND status = %s"
            params.append(status_filter)
        
        if search:
            query += " AND (LOWER(supplier) LIKE %s OR LOWER(contract_name) LIKE %s)"
            params.extend([f'%{search.lower()}%', f'%{search.lower()}%'])

        sort_col = request.args.get('sort', 'status')
        sort_order = request.args.get('order', 'asc')
        
        # Valid sort columns whitelist
        valid_cols = {
            'supplier': 'supplier',
            'contract_name': 'contract_name',
            'category': 'category',
            'status': 'status',
            'budget': 'annual_value_current',
            'invoiced': 'invoiced_ytd',
            'variance': 'variance_percentage',
            'start_date': 'start_date',
            'end_date': 'end_date'
        }
        
        db_sort = valid_cols.get(sort_col, 'status')
        db_order = 'ASC' if sort_order.lower() == 'asc' else 'DESC'

        # Custom ordering for status to prioritize critical statuses
        if db_sort == 'status':
            query += f""" ORDER BY
                CASE status
                    WHEN 'NO_CONTRACT' THEN 1
                    WHEN 'EXPIRED' THEN 2
                    WHEN 'OVERSPEND' THEN 3
                    WHEN 'UNDERUTILIZED' THEN 4
                    WHEN 'NO_ACTIVITY' THEN 5
                    WHEN 'ON_TRACK' THEN 6
                    ELSE 7
                END {db_order},
                invoiced_ytd DESC
                LIMIT 100"""
        else:
            query += f" ORDER BY {db_sort} {db_order}, status ASC LIMIT 100"
        
        cursor.execute(query, params)
        contracts = [dict(row) for row in cursor.fetchall()]
        
        # Serialize values
        for contract in contracts:
            for key, val in contract.items():
                contract[key] = serialize_value(val)
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'contracts': contracts,
            'count': len(contracts)
        })
        
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/ai/chat', methods=['POST'])
def ai_chat():
    data = request.json
    question = data.get('question', '')
    
    if not anthropic_client:
        return jsonify({
            'success': False,
            'error': 'Anthropic API key not configured. Set ANTHROPIC_API_KEY environment variable.'
        })
    
    try:
        # System prompt with database schema
        system_prompt = """You are a finance analyst for ELFT NHS Trust with access to PostgreSQL database.

DATABASE SCHEMA:
- ap_transactions: payment data with columns:
  * party (supplier name)
  * amount_gbp (transaction amount)
  * month (format: 'APR-24', 'MAY-24', etc.)
  * source ('PO', 'No PO', 'Interface Invoice', 'Payment Requested')
  * final_category (spending category - see examples below)
  * directorate (organizational unit - see examples below)
  * transaction_date, description, etc.

- contracts: contract register (supplier, contract_name, estimated_total_contract_value, start_date, end_date)

IMPORTANT - ACTUAL DATA VALUES:
Top spending categories in final_category:
- 'Estates and Facilities', 'NHS Providers', 'Private Providers', 'Voluntary Sector', 'Digital and IT', 'Agency', 'Data', 'Training', 'Supplies', 'Local Authority'

Directorates:
- 'CORPORATE', 'BEDFORDSHIRE CHS', 'Bedford Directorate', 'TOWER HAMLETS', 'ESTATES & FACILITIES', 'PRIMARY CARE', 'SPECIALIST SERVICES', 'CITY & HACKNEY', 'NEWHAM', 'Luton Directorate', etc.

Date range: APR-24 to SEP-24 (financial year 24/25)

CRITICAL INSTRUCTIONS FOR SQL QUERIES:
1. Generate ONE SQL query to get data
2. Mark SQL with "SQL_QUERY:" on its own line
3. Put ONLY the SQL code after "SQL_QUERY:" - NO explanatory text within the SQL block
4. End the SQL with a semicolon
5. Put explanations BEFORE the SQL block, never inside it
6. I will execute it and send you the results - DO NOT generate multiple queries

CORRECT Example:
To answer this, I'll query the database for agency spending.

SQL_QUERY:
SELECT SUM(amount_gbp) as total_spend, COUNT(*) as transaction_count
FROM ap_transactions
WHERE final_category = 'Agency';

WRONG Example (DO NOT DO THIS):
SQL_QUERY:
SELECT SUM(amount_gbp) as total_spend
FROM ap_transactions
WHERE final_category = 'Agency';

Let me also check the breakdown by month:
SQL_QUERY:
SELECT month, SUM(amount_gbp) as spend FROM ap_transactions WHERE final_category = 'Agency' GROUP BY month;
"""
        
        # Call Claude
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": question
            }]
        )
        
        response_text = response.content[0].text

        # Extract SQL if present - improved parsing
        sql_query = None
        if "SQL_QUERY:" in response_text:
            parts = response_text.split("SQL_QUERY:", 1)
            if len(parts) > 1:
                sql_section = parts[1]

                # Handle code blocks
                if "```" in sql_section:
                    # Extract from code block
                    code_blocks = sql_section.split("```")
                    for block in code_blocks:
                        if block.strip() and not block.strip().startswith('sql'):
                            # Remove 'sql' language identifier if present
                            sql_query = block.replace('sql\n', '').replace('sql ', '').strip()
                            break
                else:
                    # No code blocks - extract until next paragraph or end
                    # Split by double newline or look for explanation text
                    lines = sql_section.split('\n')
                    sql_lines = []
                    for line in lines:
                        stripped = line.strip()
                        # Stop at empty line followed by explanatory text
                        if not stripped and sql_lines:
                            break
                        # Skip lines that look like explanations (start with "This", "The", etc.)
                        if stripped and not any(stripped.startswith(word) for word in ['This ', 'The ', 'Here ', 'It ', 'Note:']):
                            sql_lines.append(line)
                        elif sql_lines:  # Already collecting SQL, hit explanation
                            break
                    sql_query = '\n'.join(sql_lines).strip()

                # Clean up the SQL
                if sql_query:
                    # Remove any trailing explanation text that might have slipped through
                    sql_query = sql_query.split('\n\nThis')[0].split('\n\nThe')[0].strip()
                    # Ensure it ends with semicolon
                    if not sql_query.endswith(';'):
                        sql_query += ';'
        
        # Execute SQL if found
        data_results = None
        if sql_query:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(sql_query)
                
                results = cursor.fetchall()
                columns = [desc[0] for desc in cursor.description]
                
                data_results = {
                    'columns': columns,
                    'rows': [[serialize_value(val) for val in row.values()] for row in results[:50]]
                }
                
                cursor.close()
                conn.close()
                
                # Send results back to Claude for analysis
                follow_up = anthropic_client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=4096,
                    system=system_prompt,
                    messages=[
                        {"role": "user", "content": question},
                        {"role": "assistant", "content": response_text},
                        {"role": "user", "content": f"Query executed. Results ({len(results)} rows):\n{json.dumps(data_results, indent=2)[:2000]}\n\nAnalyze these results."}
                    ]
                )
                
                response_text = follow_up.content[0].text
                
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': f'SQL execution failed: {str(e)}',
                    'sql': sql_query
                })
        
        return jsonify({
            'success': True,
            'response': response_text,
            'sql': sql_query,
            'data': data_results
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0')
