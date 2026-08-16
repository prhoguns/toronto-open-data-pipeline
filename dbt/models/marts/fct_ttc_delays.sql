select
    d.source_row_id                          as ttc_delay_key,
    to_char(d.delay_date, 'YYYYMMDD')::int   as delay_date_key,
    d.delay_date,
    d.delay_at,
    extract(hour from d.delay_at)::int       as delay_hour,
    d.station,
    d.line,
    d.bound,
    d.delay_code,
    coalesce(c.delay_description, 'Unknown code') as delay_description,
    d.delay_minutes,
    d.gap_minutes,
    d.vehicle
from {{ ref('stg_ttc_delays') }} d
left join {{ ref('dim_ttc_delay_code') }} c using (delay_code)
