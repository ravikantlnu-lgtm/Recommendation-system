WITH FilteredData AS ( --filter data for specific values on stage, Primary category, subcategory and valuation as marked by FBM
  SELECT
    *,
    SAFE_CAST(Valuation_Value AS FLOAT64) AS NumericValuation
  FROM
    `proj-docai-dev.sales_rec_demo.cc_data_total`
  WHERE
    SAFE_CAST(Valuation_Value AS FLOAT64) > 1000000
    AND Stage IN ("Biddate Set", "Construction Documents", "General Contractor Award", "Low Bids Announced", "SUBBIDS: ASAP", "Construction Underway", "Post Bid")
    AND ParentCategories_PrimaryCategoryName IN (
      "Airport", "Apartments", "Auditoriums", "Bank", "College", "University", "Condominiums", "Courthouses", "Dormitories", "Elementary, Pre Schools", "Fire and Police Stations", "Food Stores", "Government - Misc. Bldgs.", "Government Offices", "High Schools", "Hospitals, Clinics", "Hotels", "Junior High Schools", "Libraries", "Medical Offices", "Military - Misc.", "Military Housing", "Military Offices", "Museums", "Nursing Homes", "Offices", "Post Offices", "Prisons", "Religious Auditoriums", "Rental Warehouses", "Restaurants", "Retail Stores", "Shopping Centers", "Special, Vocational Schools", "Sports Arenas/Convention Centers", "Warehouses", "Athletic Bldgs", "Automotive", "Cafeterias", "Clubs, Community Centers", "Entertainment", "Golf Course / Country Club", "Laboratories", "Transportation Terminals", "Water and Sewage Treatment Plants"
    )
    AND EXISTS (SELECT 1 FROM UNNEST(ParentCategories_ParentCategory) AS pc, UNNEST(pc.`ns0:SubCategories`.`ns0:SubCategory`) as sub WHERE sub IN ("Airport","Offices","Transportation Terminals","Rental Warehouses","Museums","Sports Arenas/Convention Centers","Libraries","Auditoriums","Religious Auditoriums","Elementary, Pre Schools, High Schools, Junior High Schools, Special, Vocational Schools","College, University","Clubs, Community Centers", "Athletic Bldgs","Cafeterias","Dormitories","Courthouses","Fire and Police Stations","Prisons","Government - Misc. Bldgs.","Government Offices","Post Offices","Broadcast Studios","Warehouses","Laboratories","Hospitals, Clinics","Medical Offices","Manufacturing"))
),
ValuationBuckets AS (   --create valuatio buckets to allow for a more balanced selection across different valuation ranges.
    SELECT *, NTILE(4) OVER (ORDER BY NumericValuation) as ValuationBucket
    FROM FilteredData
),
DistinctCombos AS (  -- select data samples with distinct combos of stage, primary category, state and valuation bucket
  SELECT
    Stage,
    ParentCategories_PrimaryCategoryName,
    ValuationBucket,
    addr.`ns0:StateProvince`,
    COUNT(1) AS combo_count
  FROM
    ValuationBuckets,
    UNNEST(Addresses_Address) AS addr
  GROUP BY 1, 2, 3, 4
),
PartitionedData AS ( -- Partition by stage, primary category, state and valuation bucket
  SELECT
    fd.*,
    addr.`ns0:StateProvince`,
    fd.ValuationBucket,
    ROW_NUMBER() OVER (PARTITION BY fd.Stage, fd.ParentCategories_PrimaryCategoryName, addr.`ns0:StateProvince`, fd.ValuationBucket ORDER BY RAND()) AS rn
  FROM
    ValuationBuckets AS fd,
    UNNEST(fd.Addresses_Address) AS addr
),
TargetRows AS ( --- selecting number of rows from each partition to get total 130 rows
  SELECT
    CAST(CEIL(130 / (SELECT COUNT(1) FROM DistinctCombos)) AS INT64) AS target_per_group
),
FinalData AS (
    SELECT pd.* from PartitionedData as pd, TargetRows as tr where pd.rn <= tr.target_per_group
)
SELECT * FROM FinalData LIMIT 130;


-------
------ =QUERY(CF:CF,"select CF, count(CF) where CF is not null group by CF label count(CF) 'Count'",1)