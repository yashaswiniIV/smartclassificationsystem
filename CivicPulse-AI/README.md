# Civic Complaint Platform

A web platform where citizens report civic problems (broken pipes, potholes, garbage, street lights) by speaking or typing, and officers get a deduplicated, prioritized work queue instead of hundreds of repeated tickets.

Adapted from the open-source CivicPulse-AI project (MIT license). This version keeps the core complaint → issue funnel and removes everything else. See "Scope" for exactly what is in and out.

---

## 1. The problem

When many people report the same problem, a basic complaint system opens many tickets for one real issue. Officers waste time reading duplicates, and they cannot tell which problem affects the most people.

This platform fixes that with one idea:

- A **Complaint** is one person's report.
- An **Issue** is the real-world problem. Many complaints can belong to one issue.
- **Deduplication** means attaching a new complaint to an existing issue.
- Officers work on issues. Citizens see their own complaints.

```
many COMPLAINTS  ->  one ISSUE      ->  priority score   ->  officer queue
 (citizens)         (PostGIS +          (more reports =       (triage, resolve)
                     pgvector)           higher priority)
```

---

## 2. Scope

### In scope (the feature list)

| # | Feature | What it does |
|---|---------|--------------|
| 1 | Voice-first complaint input | Citizen taps the mic and speaks |
| 2 | Editable transcript | Speech-to-text result appears in a text box; the citizen corrects mistakes before submitting |
| 3 | Location pin / GPS | "Use my location" button plus a draggable map pin; optional typed landmark note |
| 4 | LLM classification | Free text becomes category, priority, confidence and a short officer summary |
| 5 | Structured JSON validation | Backend accepts only valid category and priority values |
| 6 | Low-confidence fallback | Invalid or uncertain AI output marks the complaint `needs_review` |
| 7 | PostGIS nearby search | Finds existing issues within a radius (default 100 m) |
| 8 | pgvector similarity | Compares complaint text embeddings to find similar wording |
| 9 | Duplicate merge with officer override | Similar nearby complaints join one issue; an officer can undo or correct a merge |
| 10 | Duplicate-driven priority bump | More reports on an issue raise its priority |
| 11 | Officer dashboard | Issue list, map, filters, duplicate count, status |
| 12 | RBAC | Citizens manage their own complaints; officers triage and resolve |
| 13 | Status workflow | `open -> in_progress -> resolved -> closed`, with timestamps |
| 14 | PostgreSQL + Alembic | Reliable storage and versioned migrations |
| 15 | Tests | Validation, dedup, priority bump, authorization |
| 16 | Docker + Railway deployment | Containerized app, public demo, seeded data |

### Modifications from the original project

- **Photos:** removed completely. No photo upload, no image storage, no vision AI.
- **Frontend:** server-rendered pages using Jinja2 + HTMX with a small amount of plain JavaScript (mic and map only). No Next.js, no TypeScript, no React.
- **Deployment:** Railway instead of Caddy on a VPS.
- **Queue:** no Redis or background worker. The AI pipeline runs as a FastAPI background task after the complaint is saved.

### Out of scope (removed on purpose)

Redis queue and AI worker, citizen notifications, daily LLM officer summary, hotspot detection, SARIMA forecasting, ward risk scores, photo/vision verification, SLA escalation engine, public accountability and closure photos, WhatsApp intake, IVR / missed-call intake, multi-agent workflow, predictive problem-area prediction, email OTP signup, and the public transparency dashboard.

---

## 3. Tech stack

| Layer | Choice | Why |
|-------|--------|-----|
| Language | Python 3.12 | You know it; best AI library support |
| API framework | FastAPI | Async, automatic validation, easy to explain |
| Validation | Pydantic v2 | Enforces the allowed category and priority values |
| Pages | Jinja2 templates + HTMX | Server-rendered, no separate frontend build |
| Browser JS | Web Speech API, Leaflet (or MapLibre) | Mic input and map pin; only a few lines each |
| Database | PostgreSQL 16 | One database for everything |
| Spatial | PostGIS + GeoAlchemy2 | "Within 100 m" queries |
| Vectors | pgvector | Cosine similarity on embeddings |
| ORM / migrations | SQLAlchemy 2 (async) + asyncpg + Alembic | Standard and well documented |
| Auth | PyJWT + Argon2, token in HttpOnly cookie | RBAC with two roles |
| Embeddings | fastembed (ONNX, runs locally, no GPU) | No paid API for embeddings |
| LLM | Gemini Flash (JSON output), with a mock mode | Cheap; mock mode lets tests run offline |
| Logging | structlog | Structured logs |
| Tests | pytest + httpx | API and logic tests |
| Container | Docker, docker-compose for local | Same image locally and on Railway |
| Hosting | Railway (web service + Postgres service) | Simple deploy from GitHub |
| CI | GitHub Actions | Runs tests on every push |

---

## 4. Architecture

```
   Browser (Chrome)                      Railway
+-----------------------+    +------------------------------------+
| Jinja2 pages + HTMX   |    |  FastAPI app (one service)         |
| - Mic (Web Speech API)| HTTP|  - Routers: auth, complaints,      |
| - Map pin (Leaflet)   +---->|    issues, officer                 |
| - Editable transcript |    |  - Services: pipeline, dedup,      |
+-----------------------+    |    priority, lifecycle             |
                             |  - AI modules: llm, embeddings     |
                             +-----------+------------------------+
                                         |
                         +---------------+----------------+
                         |                                |
                +--------v--------+              +--------v--------+
                |   PostgreSQL    |              |   Gemini API    |
                |   + PostGIS     |              | (classification)|
                |   + pgvector    |              +-----------------+
                +-----------------+
```

### Key design choices

- **One web service.** FastAPI serves both the HTML pages and the data routes. There is no separate frontend deployment.
- **One database.** PostGIS handles location and pgvector handles text similarity, so the duplicate check is a single SQL query.
- **AI runs after save.** The complaint is stored first, then the AI pipeline runs as a background task. If the AI fails, the complaint is not lost; it becomes `needs_review`.
- **The LLM is never trusted blindly.** Every response is validated against a fixed schema before anything is saved.

---

## 5. Complete workflow

### 5.1 Citizen submits a complaint

1. Citizen logs in (role: `citizen`) and opens "Report a problem".
2. Citizen taps the mic and speaks. The browser's speech recognition fills a text box. If speech recognition is unavailable, the citizen types.
3. Citizen edits the transcript to fix recognition mistakes.
4. Citizen taps "Use my location" (GPS). A map pin appears and can be dragged to adjust. An optional landmark note ("near the temple") can be typed.
5. Citizen submits. The server saves the complaint with status `received` and returns a confirmation immediately.

### 5.2 AI pipeline (runs in the background after save)

```
complaint saved
     |
     v
[1] LLM classification  ->  {category, priority, confidence, summary}
     |
     v
[2] Validate JSON with Pydantic
     |-- invalid or confidence < threshold --> mark complaint needs_review, STOP
     v
[3] Generate embedding of the complaint text
     |
     v
[4] Duplicate search (one SQL query):
     issues within 100 m (PostGIS) AND same category
     ranked by cosine similarity (pgvector)
     |
     |-- best match similarity >= threshold --> attach complaint to that issue
     |                                          duplicate_count + 1
     |                                          recompute priority
     |-- otherwise --> create a new issue (status: open) from this complaint
     v
[5] Save results, write a history row
```

### 5.3 Officer handles issues

1. Officer logs in (role: `officer`) and opens the dashboard: issue list and map, with filters for status, category and priority, and a duplicate count on each issue.
2. Issues are sorted by priority score, highest first.
3. A separate `needs_review` list shows complaints the AI was unsure about. The officer sets the category and the complaint then joins the normal flow.
4. Officer moves an issue through the status workflow. Each change writes a timestamped history row.
5. **Override:** if a merge was wrong, the officer can move a complaint out of an issue into a new issue (or into a different one). The override is recorded.

### 5.4 Citizen tracks progress

Citizen opens "My complaints", sees each complaint with its issue's current status, and can see how many others reported the same issue.

---

## 6. Data model (target schema)

```
users
  id, name, email (unique), password_hash, role ('citizen' | 'officer'), created_at

categories
  id, name           -- e.g. water leak, road, garbage, street light

issues
  id, category_id, title, summary,
  location geography(Point, 4326),
  embedding vector(384),            -- from the first complaint
  status ('open' | 'in_progress' | 'resolved' | 'closed'),
  priority ('low' | 'medium' | 'high' | 'critical'),
  priority_score integer,
  duplicate_count integer,
  assigned_to -> users.id (nullable),
  created_at, updated_at, resolved_at, closed_at

complaints
  id, user_id -> users.id, issue_id -> issues.id (nullable until processed),
  text text,
  landmark_note text (nullable),
  location geography(Point, 4326),
  embedding vector(384),
  ai_category_id, ai_priority, ai_confidence, ai_summary,
  processing_status ('received' | 'classified' | 'needs_review' | 'failed'),
  created_at

issue_status_history
  id, issue_id, from_status, to_status, changed_by -> users.id, changed_at

merge_log
  id, complaint_id, from_issue_id, to_issue_id, action ('auto_attach' | 'officer_move'),
  similarity, distance_m, done_by (nullable for auto), done_at
```

### Indexes

- GiST index on `issues.location` and `complaints.location` (spatial queries).
- HNSW or IVFFlat index on `issues.embedding` (vector queries).
- B-tree indexes on `issues.status`, `issues.priority_score`, `complaints.user_id`.

### Migrations (Alembic)

1. `0001` enable extensions (`postgis`, `vector`)
2. `0002` users and categories
3. `0003` issues and complaints
4. `0004` status history and merge log

---

## 7. Core logic details

### 7.1 LLM classification output

The LLM must return exactly this JSON:

```json
{
  "category": "water_leak",
  "priority": "high",
  "confidence": 0.86,
  "summary": "Water pipe broken near the temple; water flowing onto the road."
}
```

Pydantic rules:

- `category` must be one of the category slugs stored in the database.
- `priority` must be one of `low`, `medium`, `high`.
- `confidence` must be a number between 0 and 1.
- `summary` must be a short non-empty string.

If parsing fails, a field is invalid, or confidence is below the threshold (start at 0.5, tune on test data), the complaint is set to `needs_review`. No guessed value is ever written.

### 7.2 Duplicate detection

A new complaint matches an existing issue when all are true:

- the issue is within 100 m (`ST_DWithin` on geography),
- the issue has the same category,
- the issue is not `closed`,
- cosine similarity between embeddings is at or above the threshold.

Start values (radius 100 m, similarity 0.80) are defaults. Tune both on your sample data and record the final values and the results.

**Embedding quality check (do this first):** the default embedding model may handle some languages poorly. Test it on sample complaint pairs in the language(s) you expect before trusting it. If duplicates are not found reliably, use one of two fixes:

- translate the complaint to English with the LLM, then embed the English text, or
- switch to an embedding model with support for the language you need.

### 7.3 Priority bump

Priority rises as more people report the same issue.

- base score: low = 10, medium = 30, high = 60
- bump: + 5 per duplicate complaint, capped at +40
- score: base + bump
- priority label from score:
  - `< 30` -> low
  - `30-59` -> medium
  - `60-89` -> high
  - `>= 90` -> critical

These numbers are adjustable defaults. Keep the rule in one function (`services/priority.py`) so tests can check it directly.

### 7.4 Status workflow

```
open --> in_progress --> resolved --> closed
  ^                         |
  +-------- reopen ---------+
```

- Only officers can move an issue forward.
- Every change writes a row to `issue_status_history` with the user and the time.
- Invalid jumps (for example `open -> closed`) are rejected.

### 7.5 RBAC

| Action | Citizen | Officer |
|--------|---------|---------|
| Sign up / log in | yes | yes |
| Create a complaint | yes | no |
| View own complaints | yes | no |
| View all issues and dashboard | no | yes |
| Fix `needs_review` complaints | no | yes |
| Change issue status | no | yes |
| Override a merge | no | yes |

Officer accounts are created by seeding or a protected admin script, not by public signup.

---

## 8. Routes

### Pages (HTML)

| Route | Who | Purpose |
|-------|-----|---------|
| `GET /login`, `GET /signup` | public | Auth forms |
| `GET /report` | citizen | Mic, editable transcript, map pin |
| `GET /my` | citizen | Own complaints and issue status |
| `GET /console` | officer | Issue list, map, filters |
| `GET /console/issues/{id}` | officer | Issue detail, complaints, history, override |
| `GET /console/review` | officer | `needs_review` complaints |

### Actions (HTMX / form posts)

| Route | Who | Purpose |
|-------|-----|---------|
| `POST /auth/signup`, `POST /auth/login`, `POST /auth/logout` | public | Auth |
| `POST /complaints` | citizen | Submit a complaint |
| `POST /console/issues/{id}/status` | officer | Move status |
| `POST /console/complaints/{id}/move` | officer | Override a merge |
| `POST /console/complaints/{id}/category` | officer | Fix a `needs_review` complaint |
| `GET /health` | public | Health check |

---

## 9. Project structure

```
project/
  app/
    main.py
    core/        config.py, db.py, security.py, logging.py
    models/      user.py, issue.py, complaint.py, history.py, enums.py
    schemas/     auth.py, complaint.py, classification.py
    api/         deps.py, auth.py, complaints.py, console.py, health.py
    services/    pipeline.py, dedup.py, priority.py, lifecycle.py
    ai/          llm.py, embeddings.py
    templates/   base.html, login.html, report.html, my.html,
                 console.html, issue.html, review.html
    static/      app.js (mic + map), style.css
  alembic/       versions/0001 ... 0004
  scripts/       seed.py (categories, officer, sample complaints)
  tests/         test_classification.py, test_dedup.py,
                 test_priority.py, test_lifecycle.py, test_rbac.py
  eval/          sample_complaints.json, run_eval.py
  infra/         postgres.Dockerfile (PostGIS + pgvector)
  Dockerfile
  docker-compose.yml
  .env.example
  .github/workflows/ci.yml
  README.md
```

---

## 10. Testing

| Test file | What it proves |
|-----------|----------------|
| `test_classification.py` | Valid JSON is accepted; bad category, bad priority, missing fields, and low confidence all produce `needs_review` |
| `test_dedup.py` | A nearby, similar complaint attaches to an issue; a far one does not; a similar-wording but different-category one does not; closed issues are never matched |
| `test_priority.py` | Each duplicate raises the score; the cap works; thresholds map to the right labels |
| `test_lifecycle.py` | Allowed status moves work; invalid jumps are rejected; history rows are written |
| `test_rbac.py` | A citizen cannot open officer pages or see other users' complaints; an officer cannot create complaints |

Tests run with the LLM in mock mode so they are fast and need no API key.

### Evaluation (for your resume numbers)

Build `eval/sample_complaints.json` with 30 to 50 realistic complaints, labeled with the correct category and a "same issue" group where relevant. `run_eval.py` reports:

- classification accuracy,
- percentage sent to `needs_review`,
- duplicate-merge precision and recall at your chosen radius and threshold.

Only quote numbers you actually measured.

---

## 11. Deployment on Railway

### Services

1. **Postgres service:** deploy from `infra/postgres.Dockerfile` (a Postgres image with PostGIS and pgvector installed), with a volume attached. Check on Railway that the extensions are available.
2. **Web service:** deploy from the repo's `Dockerfile`.

### Environment variables (web service)

```
DATABASE_URL     postgresql+asyncpg://...   (from the Postgres service)
JWT_SECRET       a long random string
GEMINI_API_KEY   your key
MOCK_AI          false
COOKIE_SECURE    true
```

### Start command

```
alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

### Notes

- Download or cache the embedding model during the Docker build so the first request is not slow.
- Run `scripts/seed.py` once to add categories, an officer account and demo complaints.
- Use HTTPS (Railway provides it). Browsers require HTTPS for GPS and microphone access.

---

## 12. Build order

1. **Foundation:** FastAPI app, Postgres with extensions, Alembic, users, signup/login, RBAC.
2. **Complaints:** complaint form, save a complaint with a location, "My complaints" page.
3. **Classification:** LLM call, Pydantic validation, `needs_review` fallback, mock mode.
4. **Duplicates:** embeddings, PostGIS + pgvector query, attach or create issue, merge log.
5. **Priority bump:** scoring function and tests.
6. **Officer dashboard:** list, map, filters, issue detail, status workflow, override.
7. **Voice:** Web Speech API, editable transcript, typing fallback.
8. **Evaluation and tests:** sample data, metrics, full test pass.
9. **Docker, CI and Railway deploy:** public demo with seeded data.

If time is short, steps 1 to 6 are already a complete project. Voice (step 7) is the final differentiator.

---

## 13. Known risks and open items

- **Embedding quality:** unverified for non-English text. Test before building dedup on top of it (see 7.2).
- **Browser speech recognition:** language support varies by browser and device. Chrome works best. The typing fallback must always work.
- **Rate limiting:** the original project may use Redis for it. Decide whether to drop it or use a simple in-process limit.
- **Railway Postgres extensions:** confirm PostGIS and pgvector both work with the custom image on your Railway plan.
- **LLM cost and limits:** keep calls small (one classification per complaint) and use mock mode in tests and CI.

---

## 14. Interview talking points

- Why an Issue is separate from a Complaint, and how that makes deduplication simple.
- Why dedup uses both distance and text similarity, and how you chose 100 m and the similarity threshold.
- What happens when the LLM returns bad or uncertain output, and why you never write guessed values.
- How the officer override keeps wrong automatic merges from becoming permanent.
- How RBAC is enforced (dependency checks on every route, not just hidden buttons).
- How you measured accuracy, and what you would improve next.

### Resume bullet template (fill in only measured numbers)

> "Built a civic complaint platform with FastAPI, PostgreSQL, PostGIS and pgvector. Voice-to-text complaints are classified by an LLM with strict schema validation and a low-confidence fallback, and duplicate reports are merged by location (100 m) and semantic similarity. Added duplicate-driven priority scoring, officer override, role-based access and a status workflow. Achieved X% classification accuracy and Y% duplicate-merge precision on N test complaints; deployed on Railway with Docker and CI."

---

## 15. License and credit

Based on CivicPulse-AI by kalisingh2277, released under the MIT license. Keep the original license text and credit in your repo.
