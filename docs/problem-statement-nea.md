# Problem Statement — NEA Weather AI Prediction System

## What problem are we solving?

**NEA's current weather forecasting services provide broad, city-wide predictions** (e.g., *"Thunderstorms in the afternoon"*) **that lack the spatial and temporal granularity needed for members of public to make confident, real-time decisions** about outdoor commutes, activities, and daily planning in Singapore's hyper-local tropical climate.

Despite NEA's extensive network of meteorological sensors and access to satellite data, this wealth of raw data is not yet translated into **personalised, location-specific, and actionable weather intelligence** at the street level. As a result, the public often experiences a gap between the forecast they receive and the weather they actually encounter — leading to disrupted plans, safety concerns, and diminished trust in public weather services.

---

## What is the business value of addressing the problem?

### 1. Public Trust & Service Excellence

Delivering hyper-local, AI-driven predictions elevates NEA's reputation as a world-class weather authority, increasing public confidence and engagement with government digital services.

| Metric | Target | How to Measure | Why This Target? |
|---|---|---|---|
| Prediction Accuracy (rain/no-rain) | ≥ 85% | Confusion matrix on held-out test set, auto-generated monthly | MSS 24-hour forecast accuracy is ~80%. AI model targets 10-min nowcasting — 85% is a realistic, incremental improvement |
| User Satisfaction Score | ≥ 4.2 / 5.0 | In-app feedback popup (5% random trigger) + quarterly survey | GovTech CSAT benchmark is 3.8–4.0; 4.2 = "above average" for government digital services |
| Monthly Active Users (MAU) | ≥ 50,000 within 12 months | Firebase Analytics / App Store Connect | ~0.9% penetration of Singapore's 5.8M population; conservative vs. myENV downloads |
| Forecast vs Actual Deviation | MAE < 0.5mm | `predicted_rainfall - actual_station_reading`, automated calculation | < 0.5mm deviation = within "drizzle" margin, imperceptible to daily decision-making |
| Repeat Usage Rate | ≥ 60% | D7 retention rate in app analytics | Weather apps have high natural stickiness (daily need); 60% D7 aligns with mature weather apps |

### 2. Public Safety & Risk Reduction

Precise, real-time rainfall alerts reduce weather-related incidents for commuters, outdoor workers, and event-goers — directly supporting NEA's mandate to protect public well-being.

| Metric | Target | How to Measure | Why This Target? |
|---|---|---|---|
| Alert Lead Time | ≥ 10 min before rainfall | `timestamp(prediction) - timestamp(actual_rain_onset)`, backtested with sensor data | Model predicts 10 min ahead — giving users enough time to take shelter, bring umbrella, or reroute |
| Weather-related Incident Reduction | ↓ 15% year-on-year | Cross-reference SCDF / LTA incident database, year-over-year comparison | ~200 lightning/storm incidents per year; AI alerts reduce outdoor exposure time, 15% reduction is conservative |
| Severe Weather Detection Rate | ≥ 90% | `correctly_predicted_heavy_rain / total_heavy_rain_events` (≥20mm/h), backtested on 1 year of data | Heavy rain events cannot be missed — 90% is the public safety floor for critical weather alerts |
| False Alert Rate | ≤ 10% | `false_alarms / total_alerts`, monthly reporting | Too many false alerts cause "cry wolf" effect; 10% is the industry standard for alert systems |
| Outdoor Worker Coverage | ≥ 80% of worksites | GIS analysis: worksite coordinates vs. sensor coverage radius | Construction workers are highest-risk outdoor group; BCA registry provides worksite locations for coverage validation |

### 3. Operational Efficiency

Automating the prediction pipeline — from satellite/sensor ingestion to API delivery — reduces manual forecasting workload and enables NEA officers to focus on severe weather events and policy.

| Metric | Target | How to Measure | Why This Target? |
|---|---|---|---|
| Forecasting Automation Rate | ≥ 90% of routine forecasts | `auto_generated_forecasts / total_forecasts × 100%` | Current forecasts are manually written by officers; AI handles routine predictions, humans focus on severe weather only |
| Data Pipeline Uptime | ≥ 99.5% | Monitoring dashboard (already implemented) tracks ingestion/training/prediction uptime | 99.5% = ~1.8 days downtime/year, realistic SLA for a non-critical-infrastructure system |
| Model Retraining Frequency | Daily (automated) | Training scheduler logs + automated email reports (already implemented) | Tropical weather shifts rapidly; daily retraining keeps model current with seasonal changes |
| Manual Forecast Hours Saved | ≥ 200 officer-hours/month | Before/after workload survey + timesheet records | Assuming 10 meteorological officers × 1 hour/day saved from routine work = 200h/month |
| Incident-to-Alert Response Time | < 5 min | End-to-end timestamp: `alert_sent_at - anomaly_detected_at` | API responds in <200ms; residual delay is business approval flow — <5 min total is achievable |

### 4. Data-Driven Governance

Aggregated search and usage analytics reveal how and where the public seeks weather information, informing infrastructure planning, urban heat island studies, and climate adaptation strategies.

| Metric | Target | How to Measure | Why This Target? |
|---|---|---|---|
| Search Query Volume | Track monthly trend | `/popular-searches` API (already implemented), monthly export | No fixed target — value is in trend analysis to understand evolving public demand |
| Top Searched Locations | Dashboard of Top 50 | Search log aggregation + geographic coordinate clustering | Identifies high-demand areas for sensor placement, shelter planning, infrastructure investment |
| Weather Pattern Insights Generated | ≥ 4 reports/year | Quarterly publication record, distributed to urban planning departments | Quarterly cadence is sustainable and aligns with government planning cycles |
| Policy Recommendations Enabled | ≥ 2/year | Track which policy documents cite Weather AI analytics | Data-to-policy takes time to validate; 2/year is a pragmatic starting point |
| Data Utilisation Rate | ≥ 80% of sensor stations | `stations_used_by_model / total_NEA_stations × 100%` | NEA operates 60+ stations; ensuring most are actively consumed avoids data waste |

### 5. Economic Enablement

Accurate, granular forecasts enable downstream value for logistics, tourism, outdoor events, and F&B industries — reducing weather-induced losses estimated at **S$50–100M annually** across affected sectors.

| Metric | Target | How to Measure | Why This Target? |
|---|---|---|---|
| Estimated Weather Loss Reduction | ≥ S$10M/year | Industry surveys + partner feedback (STB, logistics associations) | 10–20% of S$50–100M estimated annual losses; conservative attribution to Weather AI |
| API Adoption by 3rd Parties | ≥ 10 enterprise partners within 12 months | API key registrations + monthly active call volume | Logistics (Grab, Lalamove), events (EventBrite), tourism (Klook) are natural early adopters |
| Event Cancellation Reduction | ↓ 20% for outdoor events | Pre/post comparison with event organisers (SportSG, PA) | Precise forecasts give organisers confidence to proceed; 20% reduction is realistic with accurate nowcasting |
| Delivery Optimisation Savings | ≥ 5% route efficiency | A/B test: routes with vs. without weather data integration | Riders can pre-emptively avoid heavy rain routes, reducing wait times and detours |
| Tourism Satisfaction Uplift | ≥ 10% improvement | STB annual tourist experience survey – weather-related satisfaction item | Tourists' top complaint is unexpected rain disrupting itineraries; forecasts enable better trip planning |

### 6. Smart Nation Alignment

Demonstrates Singapore's leadership in applying AI + IoT to public services, contributing to Smart Nation and GreenPlan 2030 sustainability objectives.

| Metric | Target | How to Measure | Why This Target? |
|---|---|---|---|
| GovTech Integration Points | ≥ 3 government apps | Signed API MOUs / integration confirmation documents | myENV, OneService, OneMap are natural targets; Weather API adds immediate value to existing apps |
| Open Data Contribution | Public API available | Listing status on data.gov.sg | Singapore's Open Data policy mandates public data sharing; weather predictions are a natural fit |
| AI Model Transparency Score | Documented & explainable | Published Model Card (data sources, bias analysis, limitations) | Singapore FEAT framework requires AI explainability; Model Card is the industry standard practice |
| Carbon Footprint Awareness | Usage in GreenPlan reporting | Citation in GreenPlan annual report | Weather data supports climate adaptation strategies — direct alignment with GreenPlan 2030 |
| Innovation Recognition | ≥ 1 award or case study | Presentation / award records at GovTech STACK, Smart Nation conferences | One innovative project should produce at least one external showcase per year |

---

## KPI Design Principles

These KPIs are designed to follow four guiding principles:

1. **Quantifiable** — Every KPI has a clear numerical target, not vague "improvements"
2. **Measurable** — Relies on system logs, API data, or existing government surveys — no additional measurement infrastructure needed
3. **Incremental** — Targets are based on industry benchmarks or realistic improvements over current baselines
4. **Attributable** — Each metric can be traced back to Weather AI's direct contribution, not external factors

---

## How does this solution address the problem?

By fusing **Himawari-9 satellite imagery** with NEA's **real-time sensor network** (temperature, humidity, rainfall, PM2.5) through a **deep learning model (CNN + LSTM)**, the platform delivers:

1. **Hyper-local predictions** — street-level rainfall forecasts (not just regional), powered by Inverse Distance Weighting across sensor stations
2. **Real-time responsiveness** — predictions in <200ms, updated with the latest 10-minute sensor readings
3. **Route-aware intelligence** — weather conditions along a commuter's path, not just at a single point
4. **Self-improving accuracy** — automated daily retraining ensures the model continuously adapts to seasonal patterns and climate shifts

> **In essence**: This solution transforms NEA's existing meteorological infrastructure into an AI-powered, public-facing intelligence layer — turning raw data into **actionable insights that save time, reduce risk, and enable better daily decisions** for every resident in Singapore.
