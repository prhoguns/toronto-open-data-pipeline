with src as (
    select * from {{ source('raw', 'ttc_subway_delays') }}
)

select
    id::bigint                                    as source_row_id,
    date::date                                     as delay_date,
    (date || ' ' || time)::timestamp               as delay_at,
    trim(day)                                      as day_of_week,
    upper(trim(station))                           as station,
    upper(trim(code))                              as delay_code,
    nullif(min_delay, '')::int                     as delay_minutes,
    nullif(min_gap, '')::int                       as gap_minutes,
    nullif(upper(trim(bound)), '')                 as bound,
    upper(trim(line))                              as line,
    nullif(trim(vehicle), '')                      as vehicle,
    _loaded_at
from src
