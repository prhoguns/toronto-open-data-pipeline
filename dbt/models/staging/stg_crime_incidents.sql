-- One row per offence per police event. Types cast, strings trimmed, nothing filtered.
-- Filtering belongs in the fact model so this view stays a faithful typed copy of the source.
with src as (
    select * from {{ source('raw', 'major_crime_indicators') }}
)

select
    id::bigint                                   as source_row_id,
    trim(event_unique_id)                         as event_id,
    report_date::date                             as report_date,
    occ_date::date                                as occurrence_date,
    nullif(occ_year, '')::int                     as occurrence_year,
    nullif(occ_hour, '')::int                     as occurrence_hour,
    trim(occ_dow)                                 as occurrence_day_of_week,
    nullif(report_hour, '')::int                  as report_hour,
    trim(division)                                as police_division,
    trim(location_type)                           as location_type,
    trim(premises_type)                           as premises_type,
    trim(ucr_code)                                as ucr_code,
    trim(ucr_ext)                                 as ucr_ext,
    trim(offence)                                 as offence,
    trim(mci_category)                            as mci_category,
    -- 'NSA' means "not specified area"; treat as unknown neighbourhood
    case when hood_158 in ('NSA', '') then null else hood_158::int end as neighbourhood_id,
    trim(neighbourhood_158)                       as neighbourhood_name_raw,
    nullif(long_wgs84, '')::double precision      as longitude,
    nullif(lat_wgs84, '')::double precision       as latitude,
    _loaded_at
from src
