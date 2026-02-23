# Antigravity Usage Report — 2026-02-23

## Overview

| Metric | Value |
|--------|-------|
| Total Conversations | 75 |
| Total Size (all conversations) | ~665 MB |
| Estimated Tokens (raw) | ~129M |
| Estimated Tokens (with context replay) | 646M ~ 1,292M |

## Current Session (#810fc540)

| Metric | Value |
|--------|-------|
| Prompts | 125 |
| Size | 17.7 MB |
| Estimated Tokens | ~3.44M |
| Rank | #16 by size |

## Top 10 Heaviest Conversations

| # | Conversation | Size | Est. Tokens | Prompts |
|---|-------------|------|-------------|---------|
| 1 | Wind Animation (b9b5dfc4) | 44.5 MB | 8.66M | — |
| 2 | Fix Map Interpolation Triangle | 40.8 MB | 7.94M | — |
| 3 | Testing Web App Features | 38.4 MB | 7.48M | 60 |
| 4 | Wind Layer Investigation (e276f199) | 33.1 MB | 6.44M | — |
| 5 | Pagination Feature (28f94424) | 29.7 MB | 5.79M | 49 |
| 6 | Unknown (b2dcee3a) | 25.8 MB | 5.02M | 90 |
| 7 | Docker Deployment Plan | 25.6 MB | 4.99M | 824 |
| 8 | Unknown (c2ef0a52) | 25.2 MB | 4.91M | 108 |
| 9 | Unknown (3147ed6d) | 25.0 MB | 4.87M | 179 |
| 10 | Unknown (a3fce4ae) | 24.3 MB | 4.72M | 86 |

## Today's Session Summary (2026-02-23)

Key accomplishments in 125 prompts:

1. **Notification System Integration** — email + telegram for download server and API server
2. **API Notifications** — all 3 forecast endpoints (`/predict`, `/predict/path`, `/smart-query`)
3. **Bug Fix: temp=0 / humidity=0** — rainfall vs temperature station ID mismatch
4. **Timezone Fixes** — download manager (UTC for NOAA, SGT for sensor), satellite frame display (SGT)
5. **Version Bump** — v0.12.0 → v0.13.0, About page updated
6. **AWS Cleanup** — personal account resources terminated ($218.71 Feb bill → $0 going forward)

## Note

> Token counts are rough estimates based on encrypted .pb file sizes.
> Actual API consumption is significantly higher due to context window replay
> (each request resends full conversation history).
