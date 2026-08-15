-- Calendar dimension, 2014-01-01 through end of next year. Generated, not loaded.
with days as (
    select generate_series('2014-01-01'::date, (date_trunc('year', current_date) + interval '2 years - 1 day')::date, '1 day')::date as date_day
)

select
    to_char(date_day, 'YYYYMMDD')::int          as date_key,
    date_day,
    extract(year from date_day)::int            as year,
    extract(quarter from date_day)::int         as quarter,
    extract(month from date_day)::int           as month,
    to_char(date_day, 'Mon')                    as month_abbr,
    date_trunc('month', date_day)::date         as month_start,
    extract(isodow from date_day)::int          as iso_day_of_week,
    to_char(date_day, 'Dy')                     as day_abbr,
    extract(isodow from date_day) in (6, 7)     as is_weekend
from days
