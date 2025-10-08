CREATE OR REPLACE TABLE `proj-docai-dev.sales_rec_demo.cc_data_margins` AS  
SELECT 'Stage' AS column_name, 'Construction Underway' AS value, 0.27865561 AS percentage UNION ALL
SELECT 'Stage', 'Construction Documents', 0.2472299 UNION ALL
SELECT 'Stage', 'Post Bid', 0.22687601 UNION ALL
SELECT 'Stage', 'General Contractor Award', 0.19437208 UNION ALL
SELECT 'Stage', 'Low Bids Announced', 0.04818392 UNION ALL
SELECT 'Stage', 'Biddate Set', 0.00396238 UNION ALL
SELECT 'Stage', 'SUBBIDS: ASAP', 0.00072009 UNION ALL

-- ParentCategories_PrimaryCategoryName distribution
SELECT 'ParentCategories_PrimaryCategoryName' AS column_name, 'Offices' AS value, 0.17540407 AS percentage UNION ALL
SELECT 'ParentCategories_PrimaryCategoryName', 'Medical Offices', 0.11394521 AS percentage UNION ALL
SELECT 'ParentCategories_PrimaryCategoryName', 'Apartments', 0.11156873 AS percentage UNION ALL
SELECT 'ParentCategories_PrimaryCategoryName', 'Fire and Police Stations', 0.08644569 AS percentage UNION ALL
SELECT 'ParentCategories_PrimaryCategoryName', 'Hospitals, Clinics', 0.08243759 AS percentage UNION ALL
SELECT 'ParentCategories_PrimaryCategoryName', 'Warehouses', 0.05279115 AS percentage UNION ALL
SELECT 'ParentCategories_PrimaryCategoryName', 'Clubs, Community Centers', 0.04954409 AS percentage UNION ALL
SELECT 'ParentCategories_PrimaryCategoryName', 'Athletic Bldgs', 0.0414212 AS percentage UNION ALL
SELECT 'ParentCategories_PrimaryCategoryName', 'Religious Auditoriums', 0.03393934 AS percentage UNION ALL
SELECT 'ParentCategories_PrimaryCategoryName', 'Sports Arenas/Convention Centers', 0.02355047 AS percentage UNION ALL
SELECT 'ParentCategories_PrimaryCategoryName', 'Transportation Terminals', 0.02230079 AS percentage UNION ALL
SELECT 'ParentCategories_PrimaryCategoryName', 'Government - Misc. Bldgs.', 0.02224174 AS percentage UNION ALL
SELECT 'ParentCategories_PrimaryCategoryName', 'Government Offices', 0.02162643 AS percentage UNION ALL
SELECT 'ParentCategories_PrimaryCategoryName', 'Libraries', 0.0183146 AS percentage UNION ALL
SELECT 'ParentCategories_PrimaryCategoryName', 'Prisons', 0.01755736 AS percentage UNION ALL
SELECT 'ParentCategories_PrimaryCategoryName', 'Dormitories', 0.01517898 AS percentage UNION ALL
SELECT 'ParentCategories_PrimaryCategoryName', 'Retail Stores', 0.01389311 AS percentage UNION ALL
SELECT 'ParentCategories_PrimaryCategoryName', 'High Schools', 0.0122853 AS percentage UNION ALL
SELECT 'ParentCategories_PrimaryCategoryName', 'Elementary, Pre Schools', 0.0114109 AS percentage UNION ALL
SELECT 'ParentCategories_PrimaryCategoryName', 'Courthouses', 0.0112947 AS percentage UNION ALL
SELECT 'ParentCategories_PrimaryCategoryName', 'Auditoriums', 0.0112366 AS percentage UNION ALL
SELECT 'ParentCategories_PrimaryCategoryName', 'Automotive', 0.00792477 AS percentage UNION ALL
SELECT 'ParentCategories_PrimaryCategoryName', 'Rental Warehouses', 0.00593596 AS percentage UNION ALL
SELECT 'ParentCategories_PrimaryCategoryName', 'Junior High Schools', 0.00514538 AS percentage UNION ALL
SELECT 'ParentCategories_PrimaryCategoryName', 'Special, Vocational Schools', 0.00451293 AS percentage UNION ALL

-- State distribution
SELECT 'State' AS column_name, 'TX' AS value, 0.26868488 AS percentage UNION ALL
SELECT 'State', 'FL', 0.06566318 UNION ALL
SELECT 'State', 'CA', 0.05696022 UNION ALL
SELECT 'State', 'NY', 0.04086971 UNION ALL
SELECT 'State', 'NC', 0.03034653 UNION ALL
SELECT 'State', 'ON', 0.02601458 UNION ALL
SELECT 'State', 'GA', 0.0247249 UNION ALL
SELECT 'State', 'OH', 0.02318947 UNION ALL
SELECT 'State', 'QC', 0.02099206 UNION ALL
SELECT 'State', 'VA', 0.02013101 UNION ALL
SELECT 'State', 'WI', 0.0187918 UNION ALL
SELECT 'State', 'IL', 0.01858606 UNION ALL
SELECT 'State', 'MA', 0.01822411 UNION ALL
SELECT 'State', 'MI', 0.01743544 UNION ALL
SELECT 'State', 'IN', 0.01586763 UNION ALL
SELECT 'State', 'OK', 0.0158562 UNION ALL
SELECT 'State', 'MO', 0.0158362 UNION ALL
SELECT 'State', 'AZ', 0.01533233 UNION ALL
SELECT 'State', 'CO', 0.01486656 UNION ALL
SELECT 'State', 'PA', 0.01453795 UNION ALL
SELECT 'State', 'TN', 0.01452938 UNION ALL
SELECT 'State', 'WA', 0.01418553 UNION ALL
SELECT 'State', 'SC', 0.01364546 UNION ALL
SELECT 'State', 'MN', 0.01341115 UNION ALL
SELECT 'State', 'UT', 0.01269296 UNION ALL

-- Valuation_buckets distribution
SELECT 'Valuation_bucket' AS column_name, '2M-5M' AS value, 0.26567213 AS percentage UNION ALL
SELECT 'Valuation_bucket', '10M-25M', 0.17028917 AS percentage UNION ALL
SELECT 'Valuation_bucket', '5M-10M', 0.16956527 AS percentage UNION ALL
SELECT 'Valuation_bucket', '1M-2M', 0.15869348 AS percentage UNION ALL
SELECT 'Valuation_bucket', '25M-50M', 0.09396565 AS percentage UNION ALL
SELECT 'Valuation_bucket', '>100M', 0.07117337 AS percentage UNION ALL
SELECT 'Valuation_bucket', '50M-100M', 0.07064093 AS percentage;