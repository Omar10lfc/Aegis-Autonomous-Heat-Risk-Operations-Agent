# Written summary (draft — keep ≤500 words)

## Problem

Extreme heat is an operational risk for U.S. logistics and insurance teams, not just a climate headline. Street-level temperatures along a delivery corridor can diverge sharply from airport “official” readings, so managers cannot tell which routes, yards, or properties actually crossed unsafe thresholds last month, or where to reroute. Spreadsheet weather pulls are too coarse, and ad-hoc API clicks do not produce an auditable recommendation.

## Who it's for

Aegis is for logistics and insurance operations managers who already own a set of U.S. sites or routes and need a ranked, source-cited action memo from a plain-English brief (example: Phoenix distribution routes last month). The demo geography is Phoenix, AZ; the pipeline is coordinate-generic for any U.S. AOI inside FortyGuard coverage and area caps.

## FortyGuard endpoints/features used

All-plans Temperature API only: `POST /v1/heatmap` (tile temperatures plus `analytic_type` snapshot / exceedance / persistence), `POST /v1/env_params` (heat index and related parameters at points, max 3 names on Basic), `POST /v1/system/fetch-api-key-usage` (credit check), and `GET /v1/status/{activity_id}` (async result). Premium endpoints are not assumed. The agent validates U.S. geography, date bounds, and AOI area before spend. LangGraph traces every node in LangSmith.

## Measured result

_To be filled after the first live Phoenix run: latency, credits consumed, eval pass rate on 10–15 briefs, and whether the memo’s citations match returned `activity_id`s and tile stats._
