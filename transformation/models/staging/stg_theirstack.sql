with source as (

    select
        SOURCE,
        RAW_PAYLOAD,
        INGESTED_AT
    from {{ source('theirstack', 'src_postings') }}

),

extracted as (

    select
        RAW_PAYLOAD:id::STRING                                      as job_id,
        SPLIT_PART(SOURCE, ':', 1)                                  as source,
        NULLIF(SPLIT_PART(SOURCE, ':', 2), '')                      as ingestion_query,
        RAW_PAYLOAD:job_title::STRING                               as job_title,
        RAW_PAYLOAD:company::STRING                                 as company_name,
        RAW_PAYLOAD:url::STRING                                     as job_url,
        TO_DATE(RAW_PAYLOAD:date_posted::STRING)                    as date_posted,
        RAW_PAYLOAD:description::STRING                             as description,
        SPLIT_PART(RAW_PAYLOAD:short_location::STRING, ',', 1)      as city,
        RAW_PAYLOAD:state_code::STRING                              as state,
        RAW_PAYLOAD:country_code::STRING                            as country,
        RAW_PAYLOAD:latitude::FLOAT                                 as latitude,
        RAW_PAYLOAD:longitude::FLOAT                                as longitude,

        case
            when RAW_PAYLOAD:remote::BOOLEAN = true  then 'remote'
            when RAW_PAYLOAD:hybrid::BOOLEAN = true  then 'hybrid'
            else 'onsite'
        end                                                         as work_model,

        case
            when UPPER(RAW_PAYLOAD:employment_statuses[0]::STRING) in ('FULL_TIME', 'FULLTIME') then 'full_time'
            when UPPER(RAW_PAYLOAD:employment_statuses[0]::STRING) in ('PART_TIME', 'PARTTIME') then 'part_time'
            when UPPER(RAW_PAYLOAD:employment_statuses[0]::STRING) in ('CONTRACT', 'CONTRACTOR') then 'contract'
            else 'other'
        end                                                         as employment_type,

        RAW_PAYLOAD:min_annual_salary_usd::FLOAT                    as salary_min,
        RAW_PAYLOAD:max_annual_salary_usd::FLOAT                    as salary_max,

        REPLACE(LOWER(RAW_PAYLOAD:seniority::STRING), ' ', '_')    as listed_seniority,

        INGESTED_AT                                                 as ingested_at

    from source

),

deduped as (

    select *
    from extracted
    qualify ROW_NUMBER() over (
        partition by job_id
        order by ingested_at desc, ingestion_query desc
    ) = 1

),

filtered as (

    select *
    from deduped
    where job_title is not null
      and description is not null
      and not REGEXP_LIKE(
            LOWER(job_title),
            '.*(senior|sr\\.?|lead|principal|staff|manager|director|vp|vice president|avp|head of|architect|chief|svp|evp|gvp|president|officer|executive|leader).*'
          )
      and not REGEXP_LIKE(LOWER(job_title), '^(orbis|owner)$')

)

select * from filtered
