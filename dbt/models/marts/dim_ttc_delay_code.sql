select
    delay_code,
    delay_description,
    system,
    -- first two letters after the system prefix group codes into a coarse cause family
    case substr(delay_code, 2, 1)
        when 'U' then 'Equipment'
        when 'R' then 'Equipment'
        else 'Other'
    end as code_family_hint
from {{ ref('ttc_delay_codes') }}
