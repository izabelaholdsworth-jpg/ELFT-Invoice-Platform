-- Clean slate
DROP VIEW IF EXISTS vw_contract_vs_invoiced CASCADE;
DROP VIEW IF EXISTS vw_suppliers_without_contracts CASCADE;
DROP VIEW IF EXISTS vw_monthly_dashboard CASCADE;
DROP VIEW IF EXISTS vw_non_po_analysis CASCADE;
DROP VIEW IF EXISTS vw_category_spend CASCADE;
DROP VIEW IF EXISTS vw_expiring_contracts CASCADE;
DROP TABLE IF EXISTS ap_transactions CASCADE;
DROP TABLE IF EXISTS contracts CASCADE;
DROP TABLE IF EXISTS suppliers CASCADE;

-- AP TRANSACTIONS TABLE (matches Excel exactly)
CREATE TABLE ap_transactions (
    transaction_id SERIAL PRIMARY KEY,
    
    -- Financial details
    subjective_name VARCHAR(255),
    amount_gbp DECIMAL(15,2),
    month VARCHAR(20),
    transaction_date DATE,
    party VARCHAR(500),
    source_transaction VARCHAR(100),
    description TEXT,
    source VARCHAR(100),
    unit_price DECIMAL(15,2),
    quantity DECIMAL(15,2),
    uom VARCHAR(50),
    
    -- Period information
    financial_year VARCHAR(20),
    period TIMESTAMP,
    month_1 VARCHAR(20),
    
    -- Organizational structure
    ward VARCHAR(100),
    directorate VARCHAR(200),
    department VARCHAR(200),
    service VARCHAR(200),
    cost_centre_description VARCHAR(300),
    
    -- Categories
    category_1 VARCHAR(100),
    category_2 VARCHAR(200),
    account_code_name_level_5 VARCHAR(200),
    account_code_name_level_6 VARCHAR(200),
    category VARCHAR(100),
    subjective_code_description VARCHAR(200),
    analysis_one_code_description VARCHAR(200),
    
    -- Spend classification
    spend_category VARCHAR(200),
    final_category VARCHAR(200),
    sub_category VARCHAR(200),
    
    -- Additional fields
    site_type VARCHAR(100),
    high VARCHAR(100),
    coding VARCHAR(100),
    non_po_flag VARCHAR(10),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Performance indexes
CREATE INDEX idx_ap_party ON ap_transactions(party);
CREATE INDEX idx_ap_date ON ap_transactions(transaction_date);
CREATE INDEX idx_ap_month ON ap_transactions(month);
CREATE INDEX idx_ap_source ON ap_transactions(source);
CREATE INDEX idx_ap_final_category ON ap_transactions(final_category);
CREATE INDEX idx_ap_non_po ON ap_transactions(non_po_flag);
CREATE INDEX idx_ap_directorate ON ap_transactions(directorate);

-- CONTRACTS TABLE (matches Excel exactly)
CREATE TABLE contracts (
    contract_id SERIAL PRIMARY KEY,
    
    -- Core contract info
    service_rag VARCHAR(10),
    subcontract_reference VARCHAR(100),
    tier VARCHAR(50),
    contract_name VARCHAR(500),
    supplier VARCHAR(500),
    documents_rag VARCHAR(10),
    start_date DATE,
    end_date DATE,
    
    -- Status flags
    overdue VARCHAR(50),
    due_to_expire_next_fy VARCHAR(50),
    days_to_work_starts INTEGER,
    months_before_work_starts INTEGER,
    
    -- Procurement details
    procurement_review_date DATE,
    procurement_review VARCHAR(200),
    rag_rating VARCHAR(200),
    revenue_capital VARCHAR(50),
    budget_codes TEXT,
    rlw VARCHAR(100),
    
    -- Organization details
    type_of_organisation VARCHAR(200),
    local_non_local VARCHAR(50),
    net_zero_strategy VARCHAR(200),
    category VARCHAR(200),
    
    -- Contract status
    extension_in_place VARCHAR(200),
    procurement_status VARCHAR(200),
    procurement_process VARCHAR(200),
    procurement_act_directive VARCHAR(200),
    terms_conditions VARCHAR(200),
    procurement_hub VARCHAR(200),
    framework_details TEXT,
    
    -- Contacts
    elft_contract_lead VARCHAR(200),
    external_lead VARCHAR(200),
    contact_details TEXT,
    internal_lead VARCHAR(200),
    finance_business_partner VARCHAR(200),
    
    -- Contract type and location
    type_of_contract VARCHAR(200),
    site VARCHAR(200),
    area VARCHAR(200),
    
    -- Budget years
    budget_1819 DECIMAL(15,2),
    budget_1920 DECIMAL(15,2),
    budget_2021 DECIMAL(15,2),
    budget_2122 DECIMAL(15,2),
    budget_2223 DECIMAL(15,2),
    budget_2324 DECIMAL(15,2),
    budget_2425 DECIMAL(15,2),
    budget_2526 DECIMAL(15,2),
    
    -- Total value
    estimated_total_contract_value DECIMAL(15,2),
    notes TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Contract indexes
CREATE INDEX idx_contract_supplier ON contracts(supplier);
CREATE INDEX idx_contract_end_date ON contracts(end_date);
CREATE INDEX idx_contract_category ON contracts(category);
CREATE INDEX idx_contract_rag ON contracts(service_rag);

-- SUPPLIERS MASTER TABLE
CREATE TABLE suppliers (
    supplier_id SERIAL PRIMARY KEY,
    supplier_name VARCHAR(500) UNIQUE NOT NULL,
    total_spend DECIMAL(15,2) DEFAULT 0,
    transaction_count INTEGER DEFAULT 0,
    has_contract BOOLEAN DEFAULT FALSE,
    non_po_percentage DECIMAL(5,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ANALYSIS VIEWS

-- 1. CONTRACT VS INVOICED
CREATE VIEW vw_contract_vs_invoiced AS
WITH current_year_spend AS (
    SELECT 
        LOWER(TRIM(party)) as supplier_clean,
        party as supplier_original,
        SUM(amount_gbp) as invoiced_ytd,
        COUNT(*) as invoice_count,
        MAX(transaction_date) as last_invoice_date,
        SUM(CASE WHEN non_po_flag = 'Y' THEN amount_gbp ELSE 0 END) as non_po_spend
    FROM ap_transactions
    WHERE transaction_date >= CURRENT_DATE - INTERVAL '12 months'
    GROUP BY party
),
calc_view AS (
    SELECT 
        c.contract_id,
        COALESCE(c.supplier, s.supplier_original, '[No Contract]') as supplier,
        c.subcontract_reference as contract_reference,
        c.contract_name,
        c.estimated_total_contract_value as contract_value,
        c.budget_2425 as annual_value_current,
        c.start_date,
        c.end_date,
        c.service_rag,
        c.category,
        COALESCE(s.invoiced_ytd, 0) as invoiced_ytd,
        COALESCE(s.invoice_count, 0) as invoice_count,
        COALESCE(s.non_po_spend, 0) as non_po_spend_ytd,
        s.last_invoice_date,
        
        -- Variance calculation
        CASE 
            WHEN c.budget_2425 > 0 AND s.invoiced_ytd IS NOT NULL THEN
                ROUND((s.invoiced_ytd - c.budget_2425) / c.budget_2425 * 100, 2)
            ELSE NULL
        END as variance_percentage,
        
        -- Status determination
        CASE 
            WHEN c.contract_id IS NULL AND s.invoiced_ytd > 10000 THEN 'NO_CONTRACT'
            WHEN c.end_date < CURRENT_DATE THEN 'EXPIRED'
            WHEN c.end_date IS NULL AND c.contract_id IS NOT NULL THEN 'NO_END_DATE'
            WHEN s.invoiced_ytd > c.budget_2425 * 1.15 THEN 'OVERSPEND'
            WHEN s.invoiced_ytd < c.budget_2425 * 0.3 AND s.invoiced_ytd > 0 THEN 'UNDERUTILIZED'
            WHEN s.invoiced_ytd IS NULL OR s.invoiced_ytd = 0 THEN 'NO_ACTIVITY'
            ELSE 'ON_TRACK'
        END as status,
        
        -- Days to expiry
        CASE 
            WHEN c.end_date IS NOT NULL THEN c.end_date - CURRENT_DATE
            ELSE NULL
        END as days_to_expiry,
        
        -- Risk flags
        CASE 
            WHEN s.non_po_spend > s.invoiced_ytd * 0.5 THEN TRUE
            ELSE FALSE
        END as high_non_po_risk

    FROM contracts c
    FULL OUTER JOIN current_year_spend s 
        ON LOWER(TRIM(c.supplier)) = s.supplier_clean
    WHERE 
        c.contract_id IS NOT NULL 
        OR (s.invoiced_ytd > 5000)
)
SELECT * FROM calc_view
ORDER BY 
    CASE 
        WHEN status = 'NO_CONTRACT' THEN 1
        WHEN status = 'EXPIRED' THEN 2
        WHEN status = 'OVERSPEND' THEN 3
        ELSE 4
    END,
    COALESCE(invoiced_ytd, 0) DESC;

-- 2. MONTHLY DASHBOARD
CREATE VIEW vw_monthly_dashboard AS
SELECT 
    month,
    COUNT(*) as total_transactions,
    COUNT(DISTINCT party) as unique_suppliers,
    SUM(amount_gbp) as total_spend,
    AVG(amount_gbp) as avg_transaction,
    SUM(CASE WHEN non_po_flag = 'Y' THEN amount_gbp ELSE 0 END) as non_po_spend,
    SUM(CASE WHEN non_po_flag = 'N' OR non_po_flag IS NULL THEN amount_gbp ELSE 0 END) as po_spend,
    ROUND(
        SUM(CASE WHEN non_po_flag = 'Y' THEN amount_gbp ELSE 0 END) / 
        NULLIF(SUM(amount_gbp), 0) * 100, 
        2
    ) as non_po_percentage
FROM ap_transactions
GROUP BY month
ORDER BY month;

-- 3. NON-PO ANALYSIS
CREATE VIEW vw_non_po_analysis AS
SELECT 
    month,
    final_category,
    directorate,
    COUNT(*) as transaction_count,
    SUM(CASE WHEN non_po_flag = 'Y' THEN amount_gbp ELSE 0 END) as non_po_spend,
    SUM(CASE WHEN non_po_flag = 'N' OR non_po_flag IS NULL THEN amount_gbp ELSE 0 END) as po_spend,
    SUM(amount_gbp) as total_spend,
    ROUND(
        (SUM(CASE WHEN non_po_flag = 'Y' THEN amount_gbp ELSE 0 END) / 
         NULLIF(SUM(amount_gbp), 0) * 100), 2
    ) as non_po_percentage
FROM ap_transactions
GROUP BY month, final_category, directorate
HAVING SUM(amount_gbp) > 0
ORDER BY month, total_spend DESC;

-- 4. SUPPLIERS WITHOUT CONTRACTS
CREATE VIEW vw_suppliers_without_contracts AS
SELECT 
    ap.party as supplier_name,
    COUNT(*) as transaction_count,
    SUM(ap.amount_gbp) as total_spend,
    AVG(ap.amount_gbp) as avg_transaction,
    MIN(ap.transaction_date) as first_transaction,
    MAX(ap.transaction_date) as last_transaction,
    ap.final_category,
    ap.directorate,
    SUM(CASE WHEN ap.non_po_flag = 'Y' THEN ap.amount_gbp ELSE 0 END) as non_po_spend,
    ROUND(
        SUM(CASE WHEN ap.non_po_flag = 'Y' THEN ap.amount_gbp ELSE 0 END) / 
        NULLIF(SUM(ap.amount_gbp), 0) * 100, 
        2
    ) as non_po_percentage
FROM ap_transactions ap
LEFT JOIN contracts c ON LOWER(TRIM(ap.party)) = LOWER(TRIM(c.supplier))
WHERE c.contract_id IS NULL
GROUP BY ap.party, ap.final_category, ap.directorate
HAVING SUM(ap.amount_gbp) > 5000
ORDER BY total_spend DESC;

-- 5. CATEGORY SPEND ANALYSIS
CREATE VIEW vw_category_spend AS
SELECT 
    final_category,
    COUNT(*) as transaction_count,
    SUM(amount_gbp) as total_spend,
    AVG(amount_gbp) as avg_transaction,
    COUNT(DISTINCT party) as supplier_count,
    SUM(CASE WHEN non_po_flag = 'Y' THEN amount_gbp ELSE 0 END) as non_po_spend,
    ROUND(
        SUM(CASE WHEN non_po_flag = 'Y' THEN amount_gbp ELSE 0 END) / 
        NULLIF(SUM(amount_gbp), 0) * 100, 
        2
    ) as non_po_percentage
FROM ap_transactions
GROUP BY final_category
HAVING SUM(amount_gbp) > 0
ORDER BY total_spend DESC;

-- 6. EXPIRING CONTRACTS
CREATE VIEW vw_expiring_contracts AS
SELECT 
    contract_id,
    supplier,
    contract_name,
    estimated_total_contract_value as contract_value,
    end_date,
    end_date - CURRENT_DATE as days_until_expiry,
    service_rag,
    category,
    elft_contract_lead,
    CASE 
        WHEN end_date < CURRENT_DATE THEN 'EXPIRED'
        WHEN end_date <= CURRENT_DATE + INTERVAL '30 days' THEN 'CRITICAL'
        WHEN end_date <= CURRENT_DATE + INTERVAL '90 days' THEN 'WARNING'
        ELSE 'ACTIVE'
    END as status_flag
FROM contracts
WHERE end_date IS NOT NULL 
  AND end_date <= CURRENT_DATE + INTERVAL '180 days'
ORDER BY end_date;

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO contract_admin;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO contract_admin;
