-- A crime cannot occur after it was reported, and nothing should be dated in the future.
select *
from {{ ref('fct_crime_incidents') }}
where occurrence_date > current_date
   or report_date > current_date
