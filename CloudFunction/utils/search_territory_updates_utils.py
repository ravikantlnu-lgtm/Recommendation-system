UPSERT_SEARCHES_QUERY="""
    MERGE INTO `{project_id}.{dataset_id}.{target_table}` t
    USING `{project_id}.{dataset_id}.{source_table}` s
        ON t.id = s.id
    WHEN MATCHED
        THEN
            UPDATE
            SET t.name = s.name,
                t.category = s.category,
                t.boolean = s.boolean,
                t.upsert_time = current_datetime()
    WHEN NOT MATCHED
        THEN
            INSERT ( id ,name ,category ,boolean ,upsert_time )
            VALUES ( s.id, s.name ,s.category ,s.boolean ,current_datetime() )
    WHEN NOT MATCHED BY SOURCE
        THEN
            DELETE
                    """

NEW_OR_MODIFIED_SEARCH_IDENTIFIER_QUERY = """
    SELECT st.id
    FROM `{project_id}.{dataset_id}.{search_staging_table}` st
    LEFT JOIN `{project_id}.{dataset_id}.{search_table}` mt ON st.id = mt.id
    WHERE mt.id IS NULL
        OR st.boolean != mt.boolean
"""

UPSERT_SEARCHES_TERRITORIES_QUERY = """
    MERGE INTO `{project_id}.{dataset_id}.{target_table}` t
    USING `{project_id}.{dataset_id}.{source_table}` s
        ON t.territory_id = s.territory_id AND t.search_id = s.search_id
    WHEN NOT MATCHED
        THEN
            INSERT ( territory_id ,search_id )
            VALUES ( s.territory_id, s.search_id )
    WHEN NOT MATCHED BY SOURCE
        THEN
            DELETE
                    """

UPSERT_TERRITORIES_QUERY = """
    MERGE INTO `{project_id}.{dataset_id}.{target_table}` t
    USING `{project_id}.{dataset_id}.{source_table}` s
        ON t.id = s.id 
    WHEN MATCHED
        THEN
            UPDATE
            SET t.name = s.name,
                t.latitude = s.latitude,
                t.longitude = s.longitude,
                t.upsert_time = current_datetime()
    WHEN NOT MATCHED
        THEN
            INSERT ( id, name, latitude,  longitude, upsert_time )
            VALUES ( s.id, s.name, s.latitude, s.longitude, current_datetime() )
    WHEN NOT MATCHED BY SOURCE
        THEN
            DELETE
"""
