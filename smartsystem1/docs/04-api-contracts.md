# API Contracts — CivicPulse AI

Base URL: `/api/v1`. FastAPI auto-generates the live OpenAPI spec at `/docs` — **do not hand-maintain OpenAPI YAML**; this document defines conventions, ownership, and shapes, and the running code is the spec.

## Conventions

| Concern | Convention |
|---|---|
| Auth | `Authorization: Bearer <access_jwt>` (15 min). Refresh JWT in httpOnly, Secure, SameSite=Lax cookie scoped to `/api/v1/auth`. |
| IDs | UUIDs. Citizen-facing references use `public_code` (`CP-2026-000123`, `ISS-2026-00042`). |
| Time | ISO-8601 UTC (`2026-06-12T09:30:00Z`). Frontend localizes. |
| Coordinates | **GeoJSON order: `[lng, lat]`** everywhere. The #1 geo bug is silently swapping these — pick one order and enforce it in Pydantic validators. |
| Pagination | `?page=1&page_size=20` → `{"items":[...], "total": 412, "page":1, "page_size":20}`. |
| Errors | `{"error": {"code": "string_enum", "message": "human readable", "details": [...]}}` with proper HTTP status. Validation errors: 422 with field paths. |
| Rate limits | 429 + `Retry-After`. Auth: 5/min/IP. Complaint create: 10/day/citizen. Similar-check: 20/min/user. |
| Idempotency | `POST /complaints` accepts optional `Idempotency-Key` header (dedupes double-taps). |
| RBAC legend | **P** public · **C** citizen · **O** official · **H** dept head · **A** admin. Enforced server-side per endpoint. |

## Endpoints

### Auth
| Method & path | Roles | Notes |
|---|---|---|
| POST `/auth/register` | P | citizen only; sends email OTP |
| POST `/auth/verify-email` | P | `{email, otp}` |
| POST `/auth/login` | P | sets refresh cookie, returns access token + profile |
| POST `/auth/refresh` | cookie | rotates refresh token; reuse-detection revokes family |
| POST `/auth/logout` | C/O/H/A | revokes session |
| GET `/auth/me` · PATCH `/auth/me` | C/O/H/A | profile, preferred_language |

### Complaints (citizen-facing)
| Method & path | Roles | Notes |
|---|---|---|
| POST `/complaints/similar-check` | C | sync; embeds text, runs dedup query; < 800 ms |
| POST `/complaints` | C | creates complaint, enqueues pipeline, returns 201 immediately |
| GET `/complaints/mine` | C | own complaints + effective issue status |
| GET `/complaints/{id}` | C(own)/O/H/A | citizens see own only |
| POST `/complaints/{id}/media/presign` | C(own) | `{mime, bytes}` → `{upload_url, object_key}`; ≤ 3 per complaint, ≤ 8 MB, image/* only |
| POST `/complaints/{id}/media/confirm` | C(own) | after direct PUT; enqueues CV + moderation |

**POST `/complaints` request/response:**
```json
// request
{
  "description": "Bada gaddha hai bus stop ke samne, do bike gir chuki hai",
  "location": {"type": "Point", "coordinates": [77.5946, 12.9716]},
  "address_text": "Opp. Indiranagar bus stop",
  "declined_intercept": true
}
// 201 response
{
  "id": "9b2f...", "public_code": "CP-2026-000124",
  "processing_status": "queued",
  "created_at": "2026-06-12T09:30:00Z"
}
```

**POST `/complaints/similar-check` response:**
```json
{
  "candidates": [{
    "issue_id": "1f0a...", "public_code": "ISS-2026-00042",
    "title": "Large pothole near Indiranagar bus stop",
    "status": "acknowledged", "complaint_count": 7, "upvote_count": 12,
    "similarity": 0.91, "distance_m": 38,
    "thumbnail_url": "https://...", 
    "last_update": "2026-06-10T14:00:00Z"
  }]
}
```

### Issues (the work unit)
| Method & path | Roles | Notes |
|---|---|---|
| GET `/issues` | O/H/A | filters: `status, category_id, department_id, ward_id, bbox, priority_min, q, sla_breached`; sort: `priority`(default)`, created_at`; officials auto-scoped to their dept+wards |
| GET `/issues/{id}` | C(linked)/O/H/A | citizens get the public view (no internal notes/reporter PII of others) |
| GET `/issues/{id}/timeline` | C(linked)/O/H/A | status history + public updates |
| PATCH `/issues/{id}/status` | O/H/A | `{to_status, note}` — server validates the state machine (F5); resolve requires note |
| POST `/issues/{id}/assign` | H/A | `{assignee_id}` |
| POST `/issues/{id}/updates` | O/H/A | `{body, photo_key, is_internal}` |
| POST `/issues/{id}/upvote` · DELETE | C | me-too + subscribe |
| POST `/issues/{id}/confirm-resolution` | C(linked) | within 7-day window |
| POST `/issues/{id}/reopen` | C(linked) | `{reason}`; once per citizen per issue |
| POST `/issues/{id}/detach-complaint` | O/H/A | `{complaint_id}` → new issue; logs `corrections(detach)` |
| POST `/issues/{id}/merge` | O/H/A | `{source_issue_id}`; logs `corrections(merge)` |
| PATCH `/issues/{id}/category` | O/H/A | logs `corrections(recategorize)` |

### Triage (official console)
| Method & path | Roles | Notes |
|---|---|---|
| GET `/triage/queue` | O/H/A | complaints `needs_manual_triage` + low-confidence AI decisions awaiting confirm |
| POST `/triage/{complaint_id}/confirm` | O/H/A | accept AI suggestion as-is |

### Analytics (dashboards read precomputed aggregates)
| Method & path | Roles | Notes |
|---|---|---|
| GET `/analytics/heatmap` | O/H/A | `?bbox&category_id&from&to` → GeoJSON FeatureCollection of weighted grid cells |
| GET `/analytics/trends` | O/H/A | `?ward_id&category_id&granularity=week` → series of new/resolved |
| GET `/analytics/departments` | A | table: open, median resolution hrs, SLA breach %, reopened % |
| GET `/analytics/hotspots` | O/H/A | clusters + `emerging: true/false` + the rate math |
| GET `/analytics/forecast` | A | `?ward_id&category_id` → 4-week SARIMA forecast + CI, or `insufficient_history` |
| GET `/analytics/wards/{id}/risk` | A | risk score + factor breakdown |

### Reports, notifications, admin, public
| Method & path | Roles | Notes |
|---|---|---|
| GET `/reports` · GET `/reports/{id}` | A/H | list + detail (md + pdf link) |
| POST `/reports/generate` | A | on-demand, async; 202 + job id |
| GET `/notifications` · POST `/notifications/read` | C/O/H/A | inbox + mark read |
| CRUD `/admin/departments`, `/admin/categories` | A | category changes re-embed prototypes |
| POST `/admin/wards/import` | A | GeoJSON FeatureCollection upload |
| POST `/admin/users/invite` | A | email invite for officials: role, dept, wards, head flag |
| GET `/admin/corrections` | A | the flywheel log (export as training data) |
| GET `/public/stats` | P | city-wide counters, anonymized |
| GET `/public/issues` | P | anonymized open/resolved issues for the transparency map (no reporter data, rounded locations) |

## Internal AI service contract

The `ai` service is **not exposed to the internet** (Docker network only).

### Sync HTTP (called by `api`)
| Endpoint | Purpose | Contract |
|---|---|---|
| POST `ai:8001/embed` | similar-check path | `{"texts": ["query: <text>", ...]}` → `{"vectors": [[...384 floats]], "model": "multilingual-e5-small"}` |
| GET `ai:8001/health` | compose healthcheck | model loaded + versions |

### Async jobs (Redis queue; payloads are the contract)
| Job | Payload | Effect |
|---|---|---|
| `process_complaint` | `{complaint_id}` | full pipeline F8: language → embed → classify → dedupe → attach/create issue → score → notify |
| `analyze_media` | `{media_id}` | CV detection + moderation → `complaint_media.cv_result` |
| `recompute_priority` | `{issue_id}` | after upvotes/attach/age tick |
| `rebuild_daily_stats` | `{day}` | nightly aggregates |
| `scan_sla` | `{}` | hourly breach scan + notifications |
| `generate_report` | `{period_start, period_end, scope}` | stats → Gemini → md/pdf → email |
| `send_notification` | `{notification_id}` | email fan-out |

Rules: every job is **idempotent** (safe to re-run), retried 3× with backoff, then parked (`needs_manual_triage` for pipeline jobs) and logged in `ai_jobs`. Jobs carry IDs, never blobs — workers re-read current state from the DB.

## Auth flow detail

```
login → 200 {access_token, user} + Set-Cookie: refresh
   access expires (15 min) → 401 {code:"token_expired"}
   → POST /auth/refresh (cookie) → new access + rotated refresh cookie
   → retry original request once
refresh reuse detected → 401 {code:"session_revoked"} → force re-login
```

Frontend keeps the access token in memory only (never localStorage — XSS). The Next.js app uses a thin fetch wrapper that handles 401→refresh→retry.

## Versioning & evolution

- Additive changes (new optional fields/endpoints) are free. Breaking changes require `/api/v2` — in practice, don't break; this is a portfolio project, keep `v1` honest.
- Pydantic response models are the single source of field truth; frontend types are generated from OpenAPI (`openapi-typescript`) in CI so drift fails the build.
