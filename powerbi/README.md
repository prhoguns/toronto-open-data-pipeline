# Power BI report

The marts are a plain star schema, so Power BI needs no transformation work — connect and model.

## Connect

1. Get Data → **PostgreSQL database**. Server `localhost:5433`, database `toronto`. Use **Import** mode.
2. Select `marts.dim_date`, `marts.dim_neighbourhood`, `marts.dim_ttc_delay_code`, `marts.fct_crime_incidents`, `marts.fct_ttc_delays`.
   Skip `geometry_geojson` from `dim_neighbourhood` in Power Query unless you are building a shape map (it is large).
3. Model view – relationships (all many-to-one, single direction, dimension side = 1):

| Fact column | Dimension column |
|---|---|
| `fct_crime_incidents[occurrence_date_key]` | `dim_date[date_key]` |
| `fct_crime_incidents[neighbourhood_id]` | `dim_neighbourhood[neighbourhood_id]` |
| `fct_ttc_delays[delay_date_key]` | `dim_date[date_key]` |
| `fct_ttc_delays[delay_code]` | `dim_ttc_delay_code[delay_code]` |

Mark `dim_date` as the date table (`date_day`).

## Measures

```dax
Incidents = COUNTROWS ( fct_crime_incidents )

Population = SUM ( dim_neighbourhood[population_2021] )

Incidents per 1000 =
DIVIDE ( [Incidents] * 1000, [Population] )

Incidents YoY % =
VAR prev = CALCULATE ( [Incidents], DATEADD ( dim_date[date_day], -1, YEAR ) )
RETURN DIVIDE ( [Incidents] - prev, prev )

Delay Events = COUNTROWS ( fct_ttc_delays )
Delay Minutes = SUM ( fct_ttc_delays[delay_minutes] )
Avg Delay Minutes = AVERAGE ( fct_ttc_delays[delay_minutes] )
Delays 10min+ = CALCULATE ( [Delay Events], fct_ttc_delays[delay_minutes] >= 10 )
```

## Pages

1. **Crime overview** – line chart Incidents by month (legend `mci_category`); card Incidents YoY %; slicer year.
2. **Neighbourhoods** – bar chart Incidents per 1000 by `neighbourhood_name` (top N 15); table with population, NIA flag; optional shape map from `geometry_geojson`.
3. **TTC delays** – matrix station × month of Delay Minutes; bar chart Delay Minutes by `delay_description`; hour-of-day histogram.
