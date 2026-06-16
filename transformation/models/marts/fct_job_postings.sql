with int_jobs as (
    select * from {{ ref('int_jobs_unioned') }}
)

select * from int_jobs
