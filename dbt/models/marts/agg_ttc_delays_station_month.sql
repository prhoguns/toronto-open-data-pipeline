select
    date_trunc('month', delay_date)::date as month_start,
    station,
    line,
    count(*)                              as delay_events,
    sum(delay_minutes)                    as total_delay_minutes,
    round(avg(delay_minutes), 2)          as avg_delay_minutes,
    max(delay_minutes)                    as max_delay_minutes,
    count(*) filter (where delay_minutes >= 10) as delays_10min_plus
from {{ ref('fct_ttc_delays') }}
group by 1, 2, 3
