CREATE OR REPLACE TABLE `proj-docai-dev.sales_rec_demo.cc_initial_sample` AS  -- Replace `your_dataset`
SELECT
  *,
  ROW_NUMBER() OVER (ORDER BY RAND()) AS rn
FROM
  `proj-docai-dev.sales_rec_demo.cc_data_filtered`;