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
    -- The source is free text: 'YU', 'YUS', 'YU/BD', 'LINE 1', 'Line 2 Bloor-Danforth'... Collapse to the three subway lines.
    case
        when upper(trim(line)) like 'YU%' or upper(trim(line)) like 'LINE 1%' then 'YU'
        when upper(trim(line)) like 'BD%' or upper(trim(line)) like 'LINE 2%' then 'BD'
        when upper(trim(line)) like 'SHP%' then 'SHP'
        else 'OTHER'
    end                                            as line_group,
    nullif(trim(vehicle), '')                      as vehicle,
    _loaded_at
from src
