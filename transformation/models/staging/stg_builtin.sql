with source as (
    select * from {{ source('raw_sources', 'builtin_postings') }}
),

renamed as (
    select
        -- Metadata
        source as integration_source,
        ingested_at,
        
        -- Native Variant Extraction & Casting
        cast(raw_payload:id as varchar) as remote_job_id,
        cast(raw_payload:title as varchar) as job_title,
        cast(raw_payload:company_name as varchar) as company_name,
        cast(raw_payload:location as varchar) as job_location,
        cast(raw_payload:description as varchar) as job_description_raw,
        
        -- Handle nested or numeric elements safely
        cast(raw_payload:salary_min as numeric(10, 2)) as salary_min,
        cast(raw_payload:salary_max as numeric(10, 2)) as salary_max,
        cast(raw_payload:posted_date as timestamp_tz) as posted_at
        
    from source
)

select * from renamed