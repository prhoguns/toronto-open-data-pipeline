with src as (
    select * from {{ source('raw', 'neighbourhoods') }}
)

select
    area_short_code::int                       as neighbourhood_id,
    trim(area_name)                            as neighbourhood_name,
    trim(classification)                       as tsns_classification,
    classification like 'Neighbourhood Improvement%'  as is_improvement_area,
    geometry                                   as geometry_geojson,
    _loaded_at
from src
