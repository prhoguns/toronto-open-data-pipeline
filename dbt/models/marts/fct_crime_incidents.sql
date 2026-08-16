-- Grain: one row per offence per event (same as source).
-- Filters: occurrences before 2014 are reported-late historical cases the dataset
-- itself warns about; they distort trend lines, so they are excluded here and only here.
select
    c.source_row_id                         as crime_incident_key,
    c.event_id,
    to_char(c.occurrence_date, 'YYYYMMDD')::int as occurrence_date_key,
    c.occurrence_date,
    c.occurrence_hour,
    to_char(c.report_date, 'YYYYMMDD')::int as report_date_key,
    c.report_date,
    (c.report_date - c.occurrence_date)     as days_to_report,
    c.neighbourhood_id,
    c.police_division,
    c.mci_category,
    c.offence,
    c.location_type,
    c.premises_type,
    c.longitude,
    c.latitude
from {{ ref('stg_crime_incidents') }} c
where c.occurrence_date >= '2014-01-01'
