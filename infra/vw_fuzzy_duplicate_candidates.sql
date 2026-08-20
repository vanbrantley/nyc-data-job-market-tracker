---------------------------------------------------------
-- VW_FUZZY_DUPLICATE_CANDIDATES
--
-- Pulled via `SELECT GET_DDL('VIEW', 'ANALYTICS_PROD.PUBLIC.VW_FUZZY_DUPLICATE_CANDIDATES')`
-- from the account it was originally hand-created in (Snowsight UI, not
-- dbt-managed — see PROJECT.md for usage/review workflow). Saved here so a
-- future account migration has a source of truth instead of relying on
-- GET_DDL against an account that may have already expired.
---------------------------------------------------------
create or replace view ANALYTICS_PROD.PUBLIC.VW_FUZZY_DUPLICATE_CANDIDATES(
	JOB_ID_A,
	TITLE_A,
	COMPANY_A,
	SOURCE_A,
	DATE_A,
	SALARY_A,
	JOB_ID_B,
	TITLE_B,
	COMPANY_B,
	SOURCE_B,
	DATE_B,
	SALARY_B,
	LOSER_JOB_ID
) COMMENT='Surfaces near-duplicate job postings (similar title/company, dates within 3 days) missed by exact-match dedup. Review manually; not auto-deleted. See PROJECT.md.'
 as
select
    a.job_id as job_id_a,
    a.job_title as title_a,
    a.company_name as company_a,
    a.source as source_a,
    a.date_posted as date_a,
    a.final_salary_min as salary_a,
    b.job_id as job_id_b,
    b.job_title as title_b,
    b.company_name as company_b,
    b.source as source_b,
    b.date_posted as date_b,
    b.final_salary_min as salary_b,
    case
        when a.final_salary_min is not null and b.final_salary_min is null then b.job_id
        when b.final_salary_min is not null and a.final_salary_min is null then a.job_id
        when (case a.source when 'builtin' then 1 when 'theirstack' then 2 when 'jsearch' then 3 end)
           < (case b.source when 'builtin' then 1 when 'theirstack' then 2 when 'jsearch' then 3 end)
            then b.job_id
        when (case b.source when 'builtin' then 1 when 'theirstack' then 2 when 'jsearch' then 3 end)
           < (case a.source when 'builtin' then 1 when 'theirstack' then 2 when 'jsearch' then 3 end)
            then a.job_id
        else b.job_id
    end as loser_job_id
from analytics_prod.public.fct_job_postings a
join analytics_prod.public.fct_job_postings b
    on a.job_id < b.job_id
    and abs(datediff('day', a.date_posted, b.date_posted)) <= 3
    and (editdistance(lower(a.job_title), lower(b.job_title))::float
         / greatest(length(a.job_title), length(b.job_title))) <= 0.15
    and (editdistance(lower(a.company_name), lower(b.company_name))::float
         / greatest(length(a.company_name), length(b.company_name))) <= 0.35;
