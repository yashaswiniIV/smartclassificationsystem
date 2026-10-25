# PRD — CivicPulse AI: Predictive Urban Governance Platform

**Status:** Draft v1 · 2026-06-12
**Owner:** Harshit
**Deployment model:** Single city per deployment (single-tenant). Multi-city is explicitly out of scope.

---

## 1. Vision

City complaint systems treat every complaint as an independent ticket. Fifty people report the same pothole; the city opens fifty tickets, fixes one hole, and closes one ticket while forty-nine citizens think they were ignored.

CivicPulse inverts this. It is a **funnel that turns noisy citizen reports into a prioritized work queue and city-level intelligence**:

```
 many COMPLAINTS  →  deduplicated ISSUES  →  prioritized WORK QUEUES  →  aggregate INTELLIGENCE
   (citizen)           (NLP + geospatial)      (scoring + SLA + routing)    (trends, hotspots, reports)
```

Every AI feature in this product maps to exactly one stage of that funnel. If a proposed feature doesn't, it's out of scope.

**The single most important design decision:** the `Issue` (the real-world problem) is a first-class entity, separate from the `Complaint` (one citizen's report of it). Every complaint belongs to exactly one issue. Duplicate detection is not a bolt-on filter — it is the act of attaching a new complaint to an existing issue instead of creating a new one. All government-facing screens operate on issues; all citizen-facing screens operate on complaints.

## 2. Problem statement

1. **Duplication** — the same physical problem generates dozens of independent tickets, wasting triage time and corrupting workload metrics.
2. **Reactive posture** — departments learn about systemic problems (a failing water line, a flooding-prone ward) only after complaint volume explodes.
3. **Blind prioritization** — tickets are processed roughly FIFO; a fallen tree near a school and a faded signboard get the same urgency.
4. **No feedback loop** — citizens don't see outcomes, so they stop reporting, so the city loses its cheapest sensor network.

## 3. Personas

| Persona | Who | Goals | Pain today |
|---|---|---|---|
| **Priya, 28, citizen** | Commutes daily, smartphone user, reports in Hindi or Hinglish | Report a problem in <60s, know it was seen, know when it's fixed | Forms in English only, no status updates, feels like a black hole |
| **Rajesh, 45, sanitation officer** | Manages 4 wards, 30–80 open items at any time | A trustworthy, prioritized queue; not 50 tickets for one garbage pile | Spends mornings manually spotting duplicates in spreadsheets |
| **Mrs. Iyer, 52, municipal commissioner (admin)** | Accountable for city-wide outcomes | Where is the city failing? Which department is slipping? What will next month look like? | Gets anecdotes and stale monthly PDFs, not live data |

## 4. Goals and success metrics

### Product metrics (measured on seeded + demo data)
| Metric | Target |
|---|---|
| Complaint submission time (open app → submitted) | < 60 s |
| Complaint → AI-triaged (categorized, deduped, scored) | < 60 s, async |
| Duplicate-intercept adoption (citizen upvotes instead of filing) | ≥ 30% of duplicate attempts |
| Dashboard load (100k seeded complaints) | p95 < 2 s |

### AI quality metrics (measured on a hand-labeled eval set — see 06-build-plan)
| Metric | Target | Notes |
|---|---|---|
| Duplicate detection precision | ≥ 0.85 | Wrong merges destroy trust; precision > recall |
| Duplicate detection recall | ≥ 0.70 | Missed dupes are caught by officials at triage |
| Category top-1 accuracy | ≥ 0.85 | On ~150 labeled complaints incl. Hindi/Hinglish |
| CV detection (pothole/garbage) | report mAP@50 honestly | Verification signal only — never blocks submission |

> **Why metrics are in the PRD:** "AI-powered" is an empty claim without numbers. The eval set is built in the same phase as the feature, not after.

## 5. Scope by release

MoSCoW per phase. A phase ships only when its Must items pass their acceptance criteria.

| Feature | MVP (P1–P3) | V1 (P4–P5) | Later |
|---|---|---|---|
| Email/password auth, JWT, RBAC (citizen/official/admin) | **Must** | | |
| Complaint submission: text + location + photos | **Must** | | |
| Multilingual input (en + hi content; en + hi UI) | **Must** (content) | Should (UI) | More languages |
| Pre-submit duplicate intercept ("this already exists — +1?") | **Must** | | |
| Async AI pipeline: embed → classify → dedupe → score | **Must** | | |
| Official triage queue with AI suggestions + corrections | **Must** | | |
| Issue lifecycle, assignment, SLA tracking, audit history | **Must** | | |
| Citizen tracking + in-app/email notifications + resolution confirm | **Must** | | |
| Heatmap, trends, department performance dashboards | **Must** | | |
| Public (no-login) transparency dashboard | Should | **Must** | |
| CV verification: pothole / garbage / waterlogging | — | **Must** (Gemini zero-shot → YOLO fine-tune) | More classes |
| Priority scoring v1 (transparent rules) | **Must** | learned re-ranker | |
| Emerging-hotspot detection | — | **Must** | |
| Trend forecasting (per ward × category, classical stats) | — | **Must** | |
| Weekly AI report (Gemini narrative + PDF + email) | — | **Must** | |
| Root-cause hypothesis generation (LLM over cluster stats) | — | Should | |
| Voice complaint input | — | — | Could |
| WhatsApp/SMS notifications | — | — | Could (cost) |
| Native mobile app | — | — | Won't (PWA instead) |
| Multi-city tenancy | — | — | Won't |
| Aadhaar/gov-ID integration, payments | — | — | Won't |

## 6. Feature specs (acceptance criteria for Musts)

### 6.1 Authentication & roles
- Citizens self-register (email + password, email OTP verification). Officials/admins are invited by an admin — **no self-serve official signup**.
- JWT access token (15 min) + rotating refresh token (7 d) in httpOnly cookie. Logout revokes the refresh token server-side.
- RBAC enforced in the API layer per endpoint (see 04-api-contracts role matrix). UI hiding is not security.
- ✅ *Accept:* a citizen token calling an official endpoint gets 403 with a structured error; refresh rotation invalidates the old token.

### 6.2 Complaint submission with duplicate intercept
- Required: description (any supported language), location (map pin; GPS prefill). Optional: up to 3 photos (≤8 MB each, presigned direct upload).
- Before final submit, the app calls `similar-check`; if open issues of the same rough category exist within ~150 m with high text similarity, show them with photos: **"Is this your problem? [+1 Upvote] [No, file new]"**.
- Upvoting subscribes the citizen to that issue's notifications and increments its priority signal.
- ✅ *Accept:* two phrasings of the same pothole ("huge pothole near bus stop" / "sadak pe bada gaddha hai bus stand ke paas") within 100 m trigger the intercept; declining still files a complaint which the pipeline may auto-attach.

### 6.3 AI pipeline (async, < 60 s)
- On submit: detect language → embed (multilingual) → categorize (embedding similarity, Gemini fallback below confidence threshold) → CV on photos → dedupe (vector + spatial + category) → auto-attach (sim ≥ 0.88 within 150 m) or create new issue → derive ward (point-in-polygon) → compute priority → notify.
- Every step is recorded in `ai_jobs` with timing and confidence. Failures retry 3× then mark the complaint `needs_manual_triage` — **AI failure never loses a complaint**.
- ✅ *Accept:* kill the worker mid-job, restart, job completes; pipeline metrics visible per complaint in the official console.

### 6.4 Official triage & issue management
- Queue sorted by priority; each item shows AI category + confidence, attachment decision, CV verification badges. One-click confirm; corrections (recategorize, detach/merge) are stored as labeled data (`corrections` log).
- Status machine: `open → acknowledged → assigned → in_progress → resolved → closed`, plus `rejected` and `reopened`. Every transition is audited (who/when/note). Resolve requires a note; after-photo encouraged.
- SLA: due date = first complaint time + category SLA hours. Breach flags the issue, notifies department head, surfaces in analytics.
- ✅ *Accept:* full lifecycle drill works end-to-end with audit trail; a wrong AI merge can be detached in ≤ 2 clicks.

### 6.5 Citizen tracking & closure loop
- Citizen sees their complaint's effective status (the issue's status), the public timeline, and gets notified on transitions.
- On `resolved`, all linked citizens are asked to confirm within 7 days: confirm → `closed`; dispute → `reopened` (one reopen per citizen per issue); silence → auto-close.
- ✅ *Accept:* reopen works and re-enters the official queue flagged as reopened.

### 6.6 Analytics (admin + department views)
- Heatmap (MapLibre heat layer fed by GeoJSON aggregate endpoint), filters: category, department, status, date range.
- Trends: weekly new vs resolved per ward/category; department table: open count, median resolution hours, SLA breach %.
- All dashboards read from precomputed daily aggregates, not raw scans.
- ✅ *Accept:* p95 < 2 s with 100k seeded complaints.

### 6.7 Predictive layer (V1)
- **Hotspots:** DBSCAN spatial clusters of open issues; *emerging* = last-14-day rate ≥ 2× trailing-8-week baseline (flagged, with the math shown in the UI tooltip — no black box).
- **Forecasts:** weekly counts per ward × category, SARIMA (statsmodels); shown only where ≥ 12 weeks of history; always with confidence interval.
- **Risk score per ward:** transparent weighted blend of open-issue density, SLA breach rate, emerging-hotspot count, forecast slope.
- ✅ *Accept:* on seeded data with an injected trend, the system flags the right ward.

### 6.8 Weekly AI report
- Cron (Mon 06:00): aggregate stats → Gemini Flash narrative (structured prompt, numbers passed in — the LLM never invents figures) → Markdown + PDF → emailed to admins, archived in-app.
- ✅ *Accept:* every number in the narrative is traceable to the stats JSON given to the model.

## 7. Non-functional requirements

| Area | Requirement |
|---|---|
| Performance | API p95 < 300 ms (non-analytics); similar-check p95 < 800 ms; pipeline < 60 s |
| Security | OWASP top-10 hygiene; argon2id password hashing; rate limits (5/min auth, 10 complaints/day/citizen); presigned uploads validated by type+size; server-side RBAC |
| Privacy | EXIF GPS stripped from publicly served images (kept internally for verification); public dashboard fully anonymized; complaint reporter identity visible only to officials/admins. Note alignment with India DPDP Act 2023 (consent, purpose limitation) |
| Reliability | Queue jobs idempotent + retried; nightly `pg_dump` to object storage; demo mode (`MOCK_AI=true`) runs fully offline |
| i18n | UI strings via next-intl (en, hi); complaint content language-agnostic via multilingual embeddings |
| Accessibility | Keyboard-navigable forms, WCAG AA contrast on dashboards |
| Cost ceiling | < $15/month (student budget): one small VM, managed/free-tier Postgres or self-hosted, Gemini Flash free tier, R2/S3 free tier, MapLibre + OSM tiles (no Google Maps billing) |

## 8. Assumptions & constraints

- Solo developer working **full-time in a 10-day sprint** with AI pair-programming (see sprint schedule in 06-build-plan.md).
- Pilot city: **Bengaluru** (confirmed); BBMP ward boundaries GeoJSON from DataMeet/OpenCity open-data sources.
- Cold start is real: analytics/forecasting demos run on a **synthetic seeded dataset** with controllable patterns (and optionally NYC 311 open data for realism experiments).
- Languages at launch: English + Hindi.

## 9. Risks & mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Scope explosion (this spec is genuinely large) | Never finishing | Phase gates in 06-build-plan; each phase is independently demoable |
| No labeled data for "AI priority prediction" | Vaporware claim | Ship transparent rule-based scoring v1; log official corrections as labels; train re-ranker only when data exists |
| Dedup threshold wrong (over/under-merging) | Trust collapse | Human confirm at triage; auto-attach only above high threshold; eval set before tuning |
| CV accuracy on messy real photos | Embarrassing demos | CV **verifies, never gates**; start with Gemini Vision zero-shot; fine-tune YOLO on RDD2022 later; report honest mAP |
| Ultralytics YOLO is AGPL-3.0 | License obligation if distributed commercially | Fine for an open-source student project (keep repo public); documented in ADR-09 with swap options |
| Gemini quota/cost/outage | Demo fails on stage | LLM behind an adapter interface; `MOCK_AI=true` deterministic mode; Flash free tier; cache by content hash |
| Forecasting with thin data | Misleading charts | Minimum-history rule (12 weeks), confidence intervals, classical models only |
| Solo-dev burnout | Abandonment | The cut-guide in 06-build-plan defines smaller "complete" stopping points |

## 10. Open questions — resolved 2026-06-12

1. ~~Pilot city?~~ **Bengaluru** (BBMP wards, DataMeet/OpenCity GeoJSON).
2. ~~Deadline?~~ **10-day full-time sprint** (no external deadline). Named cut: YOLO fine-tune → post-sprint stretch. See sprint schedule in 06-build-plan.md.
3. Email provider: **dev = OTP/notifications logged to console + MailPit-style mock; Resend free tier wired on Day 10 if an API key exists.** Nothing blocks on an external account.
