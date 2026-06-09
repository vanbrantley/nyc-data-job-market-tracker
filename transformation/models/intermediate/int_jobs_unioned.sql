with jsearch as (
    select * from {{ ref('stg_jsearch') }}
),

theirstack as (
    select * from {{ ref('stg_theirstack') }}
),

builtin as (
    select * from {{ ref('stg_builtin') }}
),

unioned as (
    select * from jsearch
    union all
    select * from theirstack
    union all
    select * from builtin
),

-- deduplicate cross-source matches, preferring builtin > theirstack > jsearch
cross_source_deduped as (

    select *
    from unioned
    qualify ROW_NUMBER() over (
        partition by LOWER(TRIM(job_title)) || ' | ' || LOWER(TRIM(company_name))
        order by
            case source
                when 'builtin'     then 1
                when 'theirstack'  then 2
                when 'jsearch'     then 3
            end
    ) = 1

),

enrichment as (

    select
        job_id,
        inferred_seniority,
        role_archetype,
        work_focus,
        is_title_inflated,
        inflation_reasoning,
        tech_stack_required,
        tech_stack_preferred,
        paradigms_required,
        paradigms_preferred,
        degree_requirement,
        years_required_min,
        years_required_max,
        salary_min                  as llm_salary_min,
        salary_max                  as llm_salary_max,
        confidence_score,
        enriched_at
    from ENRICHED.PUBLIC.JOB_ENRICHMENT

),

joined as (

    select
        j.job_id,
        j.source,
        j.ingestion_query,
        j.job_title,
        j.company_name,
        j.job_url,
        j.date_posted,
        j.description,
        j.city,
        j.state,
        j.country,
        j.latitude,
        j.longitude,
        j.work_model,
        j.employment_type,

        -- salary: prefer structured payload value, fall back to LLM estimate
        COALESCE(j.salary_min, e.llm_salary_min)   as final_salary_min,
        COALESCE(j.salary_max, e.llm_salary_max)   as final_salary_max,

        e.inferred_seniority,
        e.role_archetype,
        e.work_focus,
        e.is_title_inflated,
        e.inflation_reasoning,
        e.tech_stack_required,
        e.tech_stack_preferred,
        e.paradigms_required,
        e.paradigms_preferred,
        e.degree_requirement,
        e.years_required_min,
        e.years_required_max,
        e.confidence_score,
        e.enriched_at,

        j.ingested_at

    from cross_source_deduped j
    left join enrichment e on j.job_id = e.job_id

),

filtered as (

    select *
    from joined
    where (role_archetype != 'software_engineer' OR role_archetype IS NULL)

)

select * from filtered
