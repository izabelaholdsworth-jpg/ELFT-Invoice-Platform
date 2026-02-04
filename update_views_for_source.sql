-- Update views to use 'source' column instead of 'non_po_flag'
-- Run this with: psql -U contract_admin -d contract_management -f update_views_for_source.sql

-- Drop and recreate vw_monthly_dashboard
DROP VIEW IF EXISTS vw_monthly_dashboard CASCADE;
CREATE VIEW vw_monthly_dashboard AS
SELECT
    month,
    COUNT(*) as total_transactions,
    COUNT(DISTINCT party) as unique_suppliers,
    SUM(amount_gbp) as total_spend,
    AVG(amount_gbp) as avg_transaction,
    SUM(CASE WHEN source = 'No PO' THEN amount_gbp ELSE 0 END) as non_po_spend,
    SUM(CASE WHEN source != 'No PO' OR source IS NULL THEN amount_gbp ELSE 0 END) as po_spend,
    ROUND(
        SUM(CASE WHEN source = 'No PO' THEN amount_gbp ELSE 0 END) /
        NULLIF(SUM(amount_gbp), 0) * 100,
        2
    ) as non_po_percentage
FROM ap_transactions
GROUP BY month
ORDER BY month;

-- Drop and recreate vw_non_po_analysis
DROP VIEW IF EXISTS vw_non_po_analysis CASCADE;
CREATE VIEW vw_non_po_analysis AS
SELECT
    month,
    final_category,
    directorate,
    COUNT(*) as transaction_count,
    SUM(CASE WHEN source = 'No PO' THEN amount_gbp ELSE 0 END) as non_po_spend,
    SUM(CASE WHEN source != 'No PO' OR source IS NULL THEN amount_gbp ELSE 0 END) as po_spend,
    SUM(amount_gbp) as total_spend,
    ROUND(
        (SUM(CASE WHEN source = 'No PO' THEN amount_gbp ELSE 0 END) /
         NULLIF(SUM(amount_gbp), 0) * 100), 2
    ) as non_po_percentage
FROM ap_transactions
GROUP BY month, final_category, directorate
HAVING SUM(amount_gbp) > 0
ORDER BY month, total_spend DESC;

-- Drop and recreate vw_suppliers_without_contracts
DROP VIEW IF EXISTS vw_suppliers_without_contracts CASCADE;
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
    SUM(CASE WHEN ap.source = 'No PO' THEN ap.amount_gbp ELSE 0 END) as non_po_spend,
    ROUND(
        SUM(CASE WHEN ap.source = 'No PO' THEN ap.amount_gbp ELSE 0 END) /
        NULLIF(SUM(ap.amount_gbp), 0) * 100,
        2
    ) as non_po_percentage
FROM ap_transactions ap
LEFT JOIN contracts c ON LOWER(TRIM(ap.party)) = LOWER(TRIM(c.supplier))
WHERE c.contract_id IS NULL
GROUP BY ap.party, ap.final_category, ap.directorate
HAVING SUM(ap.amount_gbp) > 5000
ORDER BY total_spend DESC;

-- Drop and recreate vw_category_spend
DROP VIEW IF EXISTS vw_category_spend CASCADE;
CREATE VIEW vw_category_spend AS
SELECT
    final_category,
    COUNT(*) as transaction_count,
    SUM(amount_gbp) as total_spend,
    AVG(amount_gbp) as avg_transaction,
    COUNT(DISTINCT party) as supplier_count,
    SUM(CASE WHEN source = 'No PO' THEN amount_gbp ELSE 0 END) as non_po_spend,
    ROUND(
        SUM(CASE WHEN source = 'No PO' THEN amount_gbp ELSE 0 END) /
        NULLIF(SUM(amount_gbp), 0) * 100,
        2
    ) as non_po_percentage
FROM ap_transactions
GROUP BY final_category
HAVING SUM(amount_gbp) > 0
ORDER BY total_spend DESC;

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO contract_admin;

-- Verify views were created successfully
SELECT 'vw_monthly_dashboard' as view_name, COUNT(*) as row_count FROM vw_monthly_dashboard
UNION ALL
SELECT 'vw_non_po_analysis', COUNT(*) FROM vw_non_po_analysis
UNION ALL
SELECT 'vw_suppliers_without_contracts', COUNT(*) FROM vw_suppliers_without_contracts
UNION ALL
SELECT 'vw_category_spend', COUNT(*) FROM vw_category_spend;
