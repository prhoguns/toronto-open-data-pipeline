select
    n.neighbourhood_id,
    n.neighbourhood_name,
    n.tsns_classification,
    n.is_improvement_area,
    p.population_2021,
    p.median_income_2020,
    p.households_2021,
    n.geometry_geojson
from {{ ref('stg_neighbourhoods') }} n
left join {{ ref('stg_neighbourhood_profiles') }} p using (neighbourhood_id)
