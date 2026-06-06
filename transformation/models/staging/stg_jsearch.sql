with source as (

    select
        RAW_PAYLOAD,
        INGESTED_AT
    from {{ source('jsearch', 'src_postings') }}

),

extracted as (

    select
        RAW_PAYLOAD:job_id::STRING                                  as job_id,
        'jsearch'                                                   as source,
        RAW_PAYLOAD:job_title::STRING                               as job_title,
        RAW_PAYLOAD:employer_name::STRING                           as company_name,
        RAW_PAYLOAD:job_apply_link::STRING                          as job_url,
        TO_DATE(RAW_PAYLOAD:job_posted_at_datetime_utc::STRING)     as date_posted,
        RAW_PAYLOAD:job_description::STRING                         as description,
        RAW_PAYLOAD:job_city::STRING                                as city,
        RAW_PAYLOAD:job_state::STRING                               as state,
        RAW_PAYLOAD:job_country::STRING                             as country,
        RAW_PAYLOAD:job_latitude::FLOAT                             as latitude,
        RAW_PAYLOAD:job_longitude::FLOAT                            as longitude,

        case
            when LOWER(RAW_PAYLOAD:job_title::STRING) like '%remote%' then 'remote'
            when LOWER(RAW_PAYLOAD:job_title::STRING) like '%hybrid%' then 'hybrid'
            when RAW_PAYLOAD:job_is_remote::BOOLEAN = true           then 'remote'
            else 'onsite'
        end as work_model,

        case
            when UPPER(RAW_PAYLOAD:job_employment_type::STRING) in ('FULL_TIME', 'FULLTIME', 'FULL-TIME') then 'full_time'
            when UPPER(RAW_PAYLOAD:job_employment_type::STRING) in ('PART_TIME', 'PARTTIME', 'PART-TIME') then 'part_time'
            when UPPER(RAW_PAYLOAD:job_employment_type::STRING) in ('CONTRACT', 'CONTRACTOR')              then 'contract'
            else 'other'
        end as employment_type,

        case
            when UPPER(RAW_PAYLOAD:job_salary_period::STRING) = 'YEAR'
            then RAW_PAYLOAD:job_min_salary::FLOAT
        end as salary_min,

        case
            when UPPER(RAW_PAYLOAD:job_salary_period::STRING) = 'YEAR'
            then RAW_PAYLOAD:job_max_salary::FLOAT
        end as salary_max,

        INGESTED_AT as ingested_at

    from source

),

deduped as (

    select *
    from extracted
    qualify ROW_NUMBER() over (
        partition by job_id
        order by ingested_at desc
    ) = 1

),

filtered as (

    select *
    from deduped
    where job_title is not null
      and description is not null
      -- exclude senior / leadership titles
      and not REGEXP_LIKE(
            LOWER(job_title),
            '.*(senior|sr\\.?|lead|principal|staff|manager|director|vp|vice president|avp|head of|architect|chief|svp|evp|gvp|president|officer|executive|leader).*'
          )
    --   -- exclude malformed titles
    --   and not REGEXP_LIKE(LOWER(job_title), '^(orbis|owner)$')

)

select * from filtered
