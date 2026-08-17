-- Monthly incident counts and rates per 1,000 residents by neighbourhood and category.
-- Rate uses 2021 census population for every month (the only population figure at this grain).
with monthly as (
    select
        date_trunc('month', occurrence_date)::date as month_start,
        neighbourhood_id,
        mci_category,
        count(*) as incidents
    from {{ ref('fct_crime_incidents') }}
    where neighbourhood_id is not null
    group by 1, 2, 3
)

select
    m.month_start,
    m.neighbourhood_id,
    n.neighbourhood_name,
    n.is_improvement_area,
    m.mci_category,
    m.incidents,
    n.population_2021,
    round(m.incidents * 1000.0 / nullif(n.population_2021, 0), 3) as incidents_per_1000
from monthly m
join {{ ref('dim_neighbourhood') }} n using (neighbourhood_id)
