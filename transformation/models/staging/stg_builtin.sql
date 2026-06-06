with source as (

    select
        RAW_PAYLOAD,
        INGESTED_AT
    from {{ source('builtin', 'src_postings') }}

),

extracted as (

    select
        RAW_PAYLOAD:identifier:value::STRING                        as job_id,
        'builtin'                                                   as source,
        RAW_PAYLOAD:title::STRING                                   as job_title,
        RAW_PAYLOAD:hiringOrganization:name::STRING                 as company_name,
        RAW_PAYLOAD:source_url::STRING                              as job_url,
        TO_DATE(RAW_PAYLOAD:datePosted::STRING)                     as date_posted,

        -- strip HTML tags and collapse whitespace; handle common entities
        TRIM(REGEXP_REPLACE(
            REGEXP_REPLACE(
                REPLACE(
                    REPLACE(
                        REPLACE(
                            REPLACE(RAW_PAYLOAD:description::STRING, '&amp;', '&'),
                        '&nbsp;', ' '),
                    '&lt;', '<'),
                '&gt;', '>'),
            '<[^>]+>', ' '),
        '\\s+', ' '))                                               as description,

        RAW_PAYLOAD:jobLocation:address:addressLocality::STRING     as city,
        RAW_PAYLOAD:jobLocation:address:addressRegion::STRING       as state,
        RAW_PAYLOAD:jobLocation:address:addressCountry::STRING      as country,
        RAW_PAYLOAD:jobLocation:geo:latitude::FLOAT                 as latitude,
        RAW_PAYLOAD:jobLocation:geo:longitude::FLOAT                as longitude,

        case
            when UPPER(RAW_PAYLOAD:jobLocationType::STRING) = 'TELECOMMUTE'   then 'remote'
            when LOWER(RAW_PAYLOAD:title::STRING) like '%remote%'             then 'remote'
            when LOWER(RAW_PAYLOAD:title::STRING) like '%hybrid%'             then 'hybrid'
            else 'onsite'
        end                                                         as work_model,

        case
            when UPPER(RAW_PAYLOAD:employmentType::STRING) in ('FULL_TIME', 'FULLTIME') then 'full_time'
            when UPPER(RAW_PAYLOAD:employmentType::STRING) in ('PART_TIME', 'PARTTIME') then 'part_time'
            when UPPER(RAW_PAYLOAD:employmentType::STRING) in ('CONTRACT', 'CONTRACTOR') then 'contract'
            else 'other'
        end                                                         as employment_type,

        case
            when UPPER(RAW_PAYLOAD:baseSalary:value:unitText::STRING) = 'YEAR'
             and RAW_PAYLOAD:baseSalary:value:minValue::FLOAT >= 1000
            then RAW_PAYLOAD:baseSalary:value:minValue::FLOAT
        end                                                         as salary_min,

        case
            when UPPER(RAW_PAYLOAD:baseSalary:value:unitText::STRING) = 'YEAR'
             and RAW_PAYLOAD:baseSalary:value:maxValue::FLOAT >= 1000
            then RAW_PAYLOAD:baseSalary:value:maxValue::FLOAT
        end                                                         as salary_max,

        INGESTED_AT                                                 as ingested_at

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
      and not REGEXP_LIKE(
            LOWER(job_title),
            '.*(senior|sr\\.?|lead|principal|staff|manager|director|vp|vice president|avp|head of|architect|chief|svp|evp|gvp|president|officer|executive|leader).*'
          )
      and not REGEXP_LIKE(LOWER(job_title), '^(orbis|owner)$')

)

select * from filtered
