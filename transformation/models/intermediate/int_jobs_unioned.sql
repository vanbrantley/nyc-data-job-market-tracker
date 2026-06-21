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
        tech_stack_required,
        tech_stack_preferred,
        paradigms_required,
        paradigms_preferred,
        degree_requirement,
        years_required_min,
        years_required_max,
        salary_min                  as llm_salary_min,
        salary_max                  as llm_salary_max,
        acknowledges_ai,
        domain,
        explicitly_encourages_applicants,
        confidence_score,
        enriched_at
        
    from ENRICHED.PUBLIC.JOB_ENRICHMENT
    qualify ROW_NUMBER() over (
        partition by job_id
        order by enriched_at desc
    ) = 1

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
        j.listed_seniority,

        -- early_career_tier: collapsed entry+junior grouping for dashboard charts.
        -- Built from listed_seniority ONLY (no LLM input) — scoped to builtin and
        -- theirstack, which both self-report seniority as a structured field.
        -- jsearch is intentionally excluded: it has no structured seniority field,
        -- and testing showed years_required_min overlaps too heavily between
        -- junior (0-3 yrs) and mid_level (0-10 yrs) postings to safely substitute.
        case
            when j.source in ('builtin', 'theirstack')
                 and j.listed_seniority in ('entry_level', 'junior')
                then 'entry_or_junior'
            when j.source in ('builtin', 'theirstack')
                 and j.listed_seniority = 'mid_level'
                then 'mid'
            else null
        end                                          as early_career_tier,

        -- salary: prefer structured payload value, fall back to LLM estimate
        COALESCE(j.salary_min, e.llm_salary_min)   as final_salary_min,
        COALESCE(j.salary_max, e.llm_salary_max)   as final_salary_max,

        e.inferred_seniority,
        e.role_archetype,
        e.work_focus,
        e.acknowledges_ai,
        e.domain,
        e.explicitly_encourages_applicants,
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
