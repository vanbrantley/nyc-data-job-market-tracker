with int_jobs as (
    select * from {{ ref('int_jobs_unioned') }}
)

select
    job_id,
    source,
    job_title,
    company_name,
    job_url,
    date_posted,
    description,
    city,
    state,
    country,
    latitude,
    longitude,
    work_model,
    employment_type,
    final_salary_min,
    final_salary_max,
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
    confidence_score,
    enriched_at,
    ingested_at
from int_jobs
