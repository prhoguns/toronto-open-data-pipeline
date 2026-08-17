-- Guard against a population join going wrong (e.g. a 0 or tiny population producing absurd rates).
select *
from {{ ref('agg_crime_monthly_neighbourhood') }}
where incidents_per_1000 > 100
