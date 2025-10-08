WITH percentages AS (
    SELECT * from `proj-docai-dev.sales_rec_demo.cc_data_margins`
),
data AS (
    SELECT * from `proj-docai-dev.sales_rec_demo.cc_data_filtered`

),
sample_size AS (
    -- Define the sample size here.
    -- In this example, the sample size is set to 10.
    SELECT 10 AS sample_size
),
category_counts AS (
    -- Calculate the number of rows to select from each category based on the sample size and the percentages defined in the `percentages` CTE.
    SELECT p.,
           CEILING(s.sample_size * p.category_percentage) AS num_rows_to_select
    FROM percentages p CROSS JOIN sample_size s
),
seqnums AS (
    -- Assign a random sequence number to each row within each category using the `ROW_NUMBER()` function.
    SELECT d.category,
           d.item_id,
           ROW_NUMBER() OVER (PARTITION BY d.category ORDER BY NEWID()) AS seqnum,
           c.num_rows_to_select
    FROM data d JOIN category_counts c ON d.category = c.category
)
SELECT d.*
FROM data d JOIN seqnums s ON d.category = s.category AND d.item_id = s.item_id
WHERE s.seqnum <= s.num_rows_to_select
ORDER BY d.category
