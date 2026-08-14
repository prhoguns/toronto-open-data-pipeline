-- Pivot the handful of census metrics we actually use out of the ~2,600 in the long table.
with src as (
    select
        neighbourhood_number::int as neighbourhood_id,
        metric,
        nullif(value, '') as value
    from {{ source('raw', 'neighbourhood_profiles') }}
)

select
    neighbourhood_id,
    max(case when metric = 'Total - Age groups of the population - 25% sample data' then value::numeric end)::int as population_2021,
    max(case when metric = 'Median total income in 2020 ($)' then value::numeric end)::int  as median_income_2020,
    max(case when metric = 'Total - Private households by household size - 100% data' then value::numeric end)::int as households_2021
from src
group by neighbourhood_id
