# Build Plan — CivicPulse AI

**Active plan (decided 2026-06-12): a 10-day full-time sprint**, pilot city Bengaluru, with Claude Code pair-programming most of the code. The phased plan below remains the logic of the build — exit criteria and ordering are unchanged; only the calendar is compressed. **Named cut for the sprint:** YOLOv11 fine-tuning (ADR-09 step 2) becomes a post-sprint stretch goal; Gemini Vision zero-shot covers CV in the demo.

## 10-day sprint schedule

| Day | Work | Maps to |
|---|---|---|
| 1 | Repo scaffold, docker-compose (Postgres+PostGIS+pgvector, Redis, MinIO), CI, health checks green | P0 |
| 2 | Auth end-to-end (register, OTP, login, refresh rotation, RBAC) + core models + migrations | P1 |
| 3 | BBMP ward import, complaint submission API + presigned uploads (MinIO), map pin UI | P1 |
| 4 | Citizen UI (submit + track), official console v0 (status transitions + audit), in-app notifications | P1 |
| 5 | AI service + arq pipeline: e5 embeddings, categorization, dedup, issue create/attach, similar-check + intercept UX | P2 |
| 6 | Triage UI (confirm/correct/detach/merge → corrections log), priority v1, Gemini adapter + MOCK_AI, eval set + metrics | P2 |
| 7 | daily_stats job, heatmap/trends/department dashboards, public dashboard, synthetic Bengaluru seed generator | P3 |
| 8 | CV zero-shot (Gemini Vision) + moderation, SLA scan job, resolution confirm/reopen loop, weekly report | P4-lite, P5 |
| 9 | Hotspots (DBSCAN + emerging), SARIMA forecasts, ward risk scores, dashboard polish | P5 |
| 10 | Security pass, rate limits, README + demo kit, deploy (compose on Lightsail/EC2; prod-mode local if no AWS account yet) | P6 |

**Slippage rule:** if a day overruns, cut from the bottom of the sprint, not the middle — Day 9 features go before Day 8's, and Days 1–7 are the non-negotiable core (they end with the full AI spine + living dashboards). The original part-time estimate for this scope was 14–18 weeks; the sprint works because code generation is no longer the bottleneck — **your job each day is reviewing, understanding, and testing what lands, not typing**.

**The iron rule:** a phase is done when its exit criteria pass, not when its code exists. Each phase ends with a commit tag (`phase-1`, …) and a 2-minute screen recording — by the end you have a demo reel for free.

---

## Phase 0 — Foundations (1 week)

Repo + `git init`, monorepo layout from 05-architecture.md, `uv` + `pnpm` scaffolds, docker-compose (postgres+postgis+pgvector image: `pgvector/pgvector` or `postgis/postgis` + manual vector install — verify both extensions enable), Redis, hot-reload for api/frontend, Alembic baseline migration (extensions + enums), CI (ruff, pytest, eslint, tsc, docker build), pre-commit hooks, `.env.example`.

**Exit:** `docker compose up` → frontend hello page calls `GET /api/v1/health` → `{"db": true, "redis": true}`. CI green on a PR.
**You learn:** modern Python tooling (uv, ruff), compose networking, migrations-from-day-one discipline.

## Phase 1 — The civic core, no AI (2–3 weeks)

Auth end-to-end (register/OTP/login/refresh-rotation/logout, RBAC dependencies), users/departments/categories/wards models + admin CRUD, ward GeoJSON import, complaint submission (map pin via MapLibre, presigned photo upload to R2/S3), my-complaints list, official console v0 (list + manual status transitions with audit history), in-app + email notifications, seed script v0 (wards + categories + fake users).

**Exit:** Citizen registers → files complaint with photo + location → official sees it scoped to their dept/ward → transitions status (audited) → citizen gets notified. RBAC verified by tests (citizen→403 on official routes).
**You learn:** JWT internals, refresh rotation, RBAC patterns, presigned uploads, GeoAlchemy2, the discipline of building the boring 60% first.
**Trap to avoid:** do NOT start AI features with auth half-done. Every later feature stands on this floor.

## Phase 2 — The AI spine: dedup + categorization (2–3 weeks) ← the differentiator

ai-api (/embed) + ai-worker (arq) services, `process_complaint` pipeline (language detect → e5 embed → category via prototype-embedding similarity → Gemini Flash fallback under 0.65 confidence → dedup query → auto-attach ≥0.88 ∧ ≤150 m → issue create with Gemini title → ward derive → priority v1 → notify), similar-check endpoint + the duplicate-intercept UX, triage queue UI (confirm / recategorize / detach / merge — all logging to `corrections`), `MOCK_AI` mode.

**Build the eval set in week 1 of this phase, not after:** ~60 labeled duplicate pairs + ~150 categorized complaints (mix en/hi/hinglish — write them yourself from real Swachhata/311 complaint patterns). Script in `ml/eval/` prints precision/recall + confusion matrix; numbers go in the README.

**Exit:** Two differently-phrased complaints (one Hindi, one English) about the same spot within 100 m → one issue, two reporters, intercept shown to the second citizen. Eval metrics ≥ targets (dedup precision ≥0.85, category accuracy ≥0.85) or thresholds retuned. Worker killed mid-job recovers idempotently.
**You learn:** embeddings + multilingual NLP, vector search with filters, queue idempotency/retries, threshold tuning against a labeled set, human-in-the-loop design.

## Phase 3 — Analytics that feel alive (2 weeks)

`daily_stats` nightly job + backfill, heatmap endpoint (grid aggregation) + MapLibre heat layer, trends (Recharts — pairs with shadcn), department performance table, public transparency dashboard (anonymized), seed script v1: **synthetic city generator** — Poisson arrivals per ward×category with seasonality (monsoon → waterlogging spike), injected hotspots and trends, 12+ months of history, so every dashboard and later forecast has real-looking structure you control.

**Exit:** Dashboards p95 < 2 s on 100k seeded complaints; heatmap filterable; public page needs no login and leaks no PII.
**You learn:** pre-aggregation (the #1 dashboard performance lesson), geospatial visualization, designing synthetic data that doesn't look fake.

## Phase 4 — Computer vision (2–3 weeks)

Step 1 (days): Gemini Vision zero-shot via the llm adapter — classify photo {pothole, garbage, waterlogging, other/spam} + severity + moderation; wire into `analyze_media`, badges in triage UI, CV factor into priority.
Step 2 (the real ML): fine-tune YOLOv11n on RDD2022 (potholes/cracks — has India imagery) + TACO/Roboflow garbage set; export; CPU inference in ai-worker; bounding-box overlays in console; honest mAP@50 in README; Gemini stays as fallback for classes YOLO doesn't cover.

**Exit:** Pothole photo upload → boxes drawn in triage view, severity flows into priority, junk image gets flagged. mAP reported per class. AGPL note in repo LICENSE section (ADR-09).
**You learn:** transfer learning, dataset curation/augmentation, CV evaluation, deploying models on CPU, zero-shot-vs-fine-tuned trade-offs — interview gold.

## Phase 5 — Predictive layer + reports (2–3 weeks)

Emerging-hotspot job (DBSCAN clusters + rate-ratio vs trailing baseline), SARIMA weekly forecasts per ward×category (statsmodels; only where ≥12 weeks history; with CIs), ward risk scores (transparent weighted blend), weekly report job (stats → Gemini narrative → md + WeasyPrint PDF → Resend email → archive), root-cause hypothesis button (LLM over cluster aggregates, clearly labeled as hypothesis).

**Exit:** Seeded injected trend → correct ward flagged before its volume peaks (show this in the demo!). Monday report lands in inbox; every number in prose traceable to `reports.stats`. Forecast charts show uncertainty bands.
**You learn:** classical time series done honestly, statistical alerting, LLM-as-narrator (not oracle) pattern.

## Phase 6 — Hardening + AWS (1–2 weeks)

Security checklist from 05-architecture.md top to bottom, rate limits, Sentry, structured logs, pg_dump nightly → object storage, Lightsail/EC2 deploy with compose.prod + Caddy auto-HTTPS, domain, UptimeRobot, load sanity check (locust: 50 concurrent citizens), README polish (architecture diagram, metrics table, demo GIFs), demo video.

**Exit:** Public URL, HTTPS, survives the load test, restore-from-backup rehearsed once, README that a recruiter understands in 90 seconds.

---

## If the deadline arrives early — cut from the bottom

| Time you have | Ship through | You still have |
|---|---|---|
| 4–5 weeks | P2 (+ heatmap only from P3) | The novel thing: multilingual dedup + intercept + triage flywheel |
| 8–10 weeks | P3 + P4 step 1 | + living dashboards, zero-shot CV verification |
| 12–14 weeks | P4–P5 | + fine-tuned YOLO, forecasts, AI reports |
| 16–18 weeks | P6 | + deployed, hardened, load-tested |

Never cut: the eval set (P2). Numbers are what separate "AI-powered" from "AI-flavored".

## Demo-day kit (build during P3, not the night before)

- `just demo` / `make demo`: compose up + seed + `MOCK_AI=true` — full product, zero network, zero API keys.
- Three scripted stories: (1) Hindi + English duplicate → one issue + intercept; (2) official triage correcting an AI miss (shows human-in-the-loop, builds trust); (3) admin: emerging hotspot → root-cause hypothesis → weekly report PDF.
- Seeded data tells one coherent story: "Ward 12 waterlogging is trending 3 weeks before monsoon peak."

## What each phase lets you claim truthfully (resume/interview)

- P1: "Designed and built JWT auth with rotating refresh tokens and row-scoped RBAC for a 3-role civic platform."
- P2: "Built a multilingual duplicate-detection pipeline (multilingual-e5 + pgvector + PostGIS) achieving 0.8x precision on a hand-labeled eval set; reduced redundant tickets by merging complaints into issues."
- P3: "Designed pre-aggregated geospatial analytics serving city heatmaps over 100k records at p95 < 2 s."
- P4: "Fine-tuned YOLOv11 on RDD2022 for road-damage detection (mAP@50 = 0.xx), deployed CPU inference in an async worker."
- P5: "Implemented emerging-hotspot detection and SARIMA forecasting with confidence intervals; LLM-narrated weekly reports with zero hallucinated figures by construction."
- P6: "Deployed a 5-service Dockerized platform to AWS with auto-TLS, backups, and load-tested capacity."

## Standing risks while building

| Watch for | Counter |
|---|---|
| Gold-plating the frontend before P2 | shadcn defaults are fine; the AI spine is the product |
| Tuning dedup thresholds by anecdote | Only against the eval set |
| LLM calls creeping into the request path | All Gemini calls live in worker jobs (only /embed is sync, and it's local) |
| Secrets in compose files / notebooks | env only; pre-commit secret scan |
| "One more feature" before a phase exit | The exit criteria are the feature |
