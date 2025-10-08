DECLARE iteration_count INT64 DEFAULT 0;
DECLARE max_iterations INT64 DEFAULT 12;  -- Adjust as needed

WHILE iteration_count < max_iterations DO
  -- Calculate sums of weights for each category
  CREATE OR REPLACE TEMP TABLE weight_sums AS
  SELECT
    iteration,
    Stage,
    State,
    ParentCategories_PrimaryCategoryName,
    valuation_bucket,
    COALESCE(SUM(weight), 0.000001) AS sum_weight
  FROM
    `proj-docai-dev.sales_rec_demo.raking_iterations`
  WHERE iteration = iteration_count
  GROUP BY 1, 2, 3, 4, 5;

  -- Weight adjustment logic - separate UPDATE statements for each iteration
  IF iteration_count = 0 THEN
    UPDATE `proj-docai-dev.sales_rec_demo.raking_iterations` AS t1
    SET weight = weight * (
      SELECT t2.percentage
      FROM `proj-docai-dev.sales_rec_demo.cc_data_margins` AS t2
      WHERE t2.column_name = 'Stage' AND t2.value = t1.Stage
    ) / (
      SELECT t3.sum_weight
      FROM weight_sums AS t3
      WHERE t3.iteration = t1.iteration
        AND t3.Stage = t1.Stage
    )
    WHERE t1.iteration = iteration_count;

  ELSEIF iteration_count = 1 THEN
    UPDATE `proj-docai-dev.sales_rec_demo.raking_iterations` AS t1
    SET weight = weight * (
      SELECT t2.percentage
      FROM `proj-docai-dev.sales_rec_demo.cc_data_margins` AS t2
      WHERE t2.column_name = 'State' AND t2.value = t1.State
    ) / (
      SELECT t3.sum_weight
      FROM weight_sums AS t3
      WHERE t3.iteration = t1.iteration
        AND t3.State = t1.State
    )
    WHERE t1.iteration = iteration_count;

  ELSEIF iteration_count = 2 THEN
    UPDATE `proj-docai-dev.sales_rec_demo.raking_iterations` AS t1
    SET weight = weight * (
      SELECT t2.percentage
      FROM `proj-docai-dev.sales_rec_demo.cc_data_margins` AS t2
      WHERE t2.column_name = 'ParentCategories_PrimaryCategoryName' AND t2.value = t1.ParentCategories_PrimaryCategoryName
    ) / (
      SELECT t3.sum_weight
      FROM weight_sums AS t3
      WHERE t3.iteration = t1.iteration
        AND t3.ParentCategories_PrimaryCategoryName = t1.ParentCategories_PrimaryCategoryName
    )
    WHERE t1.iteration = iteration_count;

  ELSEIF iteration_count = 3 THEN
    UPDATE `proj-docai-dev.sales_rec_demo.raking_iterations` AS t1
    SET weight = weight * (
      SELECT t2.percentage
      FROM `proj-docai-dev.sales_rec_demo.cc_data_margins` AS t2
      WHERE t2.column_name = 'Valuation_bucket' AND t2.value = t1.valuation_bucket
    ) / (
      SELECT t3.sum_weight
      FROM weight_sums AS t3
      WHERE t3.iteration = t1.iteration
        AND t3.valuation_bucket = t1.valuation_bucket
    )
    WHERE t1.iteration = iteration_count;

  END IF;

  SET iteration_count = iteration_count + 1;
END WHILE;