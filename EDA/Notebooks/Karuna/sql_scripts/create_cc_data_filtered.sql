CREATE OR REPLACE TABLE `proj-docai-dev.sales_rec_demo.cc_data_filtered` AS  
SELECT
  t.*,
  SAFE_CAST(t.Valuation_Value AS FLOAT64) AS NumericValuation,
  address.`ns0:AddressLine1` as AddresLine1,
  address.`ns0:AddressLine2` as AddressLine2,
  address.`ns0:City` as City,
  address.`ns0:CountryRegion` as Country,
  address.`ns0:County` as County,
  address.`ns0:StateProvince` as State,
  address.`ns0:ZipPostalCode` as Zipcode,
  address.`ns0:Latitude` as Latitude,
  address.`ns0:Longitude` as Longitude,
  CASE
    WHEN SAFE_CAST(t.Valuation_Value AS FLOAT64) >= 1000000 AND SAFE_CAST(t.Valuation_Value AS FLOAT64) < 2000000 THEN '1M-2M'
    WHEN SAFE_CAST(t.Valuation_Value AS FLOAT64) >= 2000000 AND SAFE_CAST(t.Valuation_Value AS FLOAT64) < 5000000 THEN '2M-5M'
    WHEN SAFE_CAST(t.Valuation_Value AS FLOAT64) >= 5000000 AND SAFE_CAST(t.Valuation_Value AS FLOAT64) < 10000000 THEN '5M-10M'
    WHEN SAFE_CAST(t.Valuation_Value AS FLOAT64) >= 10000000 AND SAFE_CAST(t.Valuation_Value AS FLOAT64) < 25000000 THEN '10M-25M'
    WHEN SAFE_CAST(t.Valuation_Value AS FLOAT64) >= 25000000 AND SAFE_CAST(t.Valuation_Value AS FLOAT64) < 50000000 THEN '25M-50M'
    WHEN SAFE_CAST(t.Valuation_Value AS FLOAT64) >= 50000000 AND SAFE_CAST(t.Valuation_Value AS FLOAT64) < 100000000 THEN '50M-100M'
    WHEN SAFE_CAST(t.Valuation_Value AS FLOAT64) >= 100000000 THEN '>100M'
    ELSE NULL
  END AS valuation_bucket
FROM
  `sales_rec_demo.cc_data_total` AS t,
  UNNEST(t.Addresses_Address) AS address
WHERE
  SAFE_CAST(t.Valuation_Value AS FLOAT64) > 1000000
  AND t.Stage IN ("Biddate Set", "Construction Documents", "General Contractor Award", "Low Bids Announced", "SUBBIDS: ASAP", "Construction Underway", "Post Bid")
  AND t.ParentCategories_PrimaryCategoryName IN (
    "Airport", "Apartments", "Auditoriums", "Bank", "College", "University", "Condominiums", "Courthouses", "Dormitories", "Elementary, Pre Schools", "Fire and Police Stations", "Food Stores", "Government - Misc. Bldgs.", "Government Offices", "High Schools", "Hospitals, Clinics", "Hotels", "Junior High Schools", "Libraries", "Medical Offices", "Military - Misc.", "Military Housing", "Military Offices", "Museums", "Nursing Homes", "Offices", "Post Offices", "Prisons", "Religious Auditoriums", "Rental Warehouses", "Restaurants", "Retail Stores", "Shopping Centers", "Special, Vocational Schools", "Sports Arenas/Convention Centers", "Warehouses", "Athletic Bldgs", "Automotive", "Cafeterias", "Clubs, Community Centers", "Entertainment", "Golf Course / Country Club", "Laboratories", "Transportation Terminals", "Water and Sewage Treatment Plants"
  )
  AND EXISTS (
    SELECT
      1
    FROM
      UNNEST(t.ParentCategories_ParentCategory) AS pc,
      UNNEST(pc.`ns0:SubCategories`.`ns0:SubCategory`) AS sub
    WHERE
      sub IN (
        "Airport", "Offices", "Transportation Terminals", "Rental Warehouses", "Museums", "Sports Arenas/Convention Centers", "Libraries", "Auditoriums", "Religious Auditoriums", "Elementary, Pre Schools, High Schools, Junior High Schools, Special, Vocational Schools", "College, University", "Clubs, Community Centers", "Athletic Bldgs", "Cafeterias", "Dormitories", "Courthouses", "Fire and Police Stations", "Prisons", "Government - Misc. Bldgs.", "Government Offices", "Post Offices", "Broadcast Studios", "Warehouses", "Laboratories", "Hospitals, Clinics", "Medical Offices", "Manufacturing"
      )
  );