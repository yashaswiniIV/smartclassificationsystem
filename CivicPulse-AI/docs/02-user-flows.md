# User Flows — CivicPulse AI

Flows are numbered F1–F8. Mermaid renders on GitHub and in VS Code (Markdown Preview Mermaid extension).

---

## F1 — Citizen registration & login

```mermaid
flowchart TD
    A[Landing page] --> B{Has account?}
    B -- No --> C[Register: name, email, password, preferred language]
    C --> D[Email OTP sent]
    D --> E{OTP valid?}
    E -- No, 3 tries --> D
    E -- Yes --> F[Account active]
    B -- Yes --> G[Login]
    G --> H{Credentials ok?}
    H -- No --> G
    H -- Yes --> I[Access token 15m + refresh cookie 7d]
    F --> I
    I --> J[Citizen home: My complaints + Report button]
```

Notes:
- Officials and admins never appear in this flow — they are invited (F7) and land on `/console`.
- Rate limit: 5 login attempts/min/IP. Generic "invalid credentials" error (no user enumeration).
- Refresh token rotates on every use; reuse of a rotated token revokes the whole session family (standard rotation defense).

---

## F2 — Submit complaint (the core flow — with duplicate intercept)

```mermaid
flowchart TD
    A[Tap Report] --> B[Pin location on map - GPS prefill]
    B --> C[Add photos 0-3 - direct upload via presigned URL]
    C --> D[Describe in any language - en/hi/hinglish]
    D --> E[App calls POST /complaints/similar-check]
    E --> F{Similar open issues nearby?}
    F -- Yes --> G[Show top 3 with photo, distance, status, reporter count]
    G --> H{It's the same problem?}
    H -- Yes --> I[+1 Upvote issue
subscribe to updates]
    I --> J[Done - no new complaint created]
    H -- No --> K[POST /complaints]
    F -- No --> K
    K --> L[201 - complaint visible immediately, status: processing]
    L --> M[Async AI pipeline runs - F8]
    M --> N[Notification: categorized + linked, or needs manual triage]
```

Design rules:
- **The intercept is a suggestion, never a wall.** "No, file new" is always available — false-positive matches must not block reporting.
- Similar-check needs: same coarse category guess (optional), within 150 m, open issues only, text cosine similarity ≥ 0.78 to even show. Show at most 3.
- Photos upload while the user types (presigned PUT direct to object storage) — perceived speed.
- Edge cases: offline → queue submission locally (PWA, later); no GPS → manual pin required; submission with no similar-check call (API consumers) is fine — the pipeline still dedupes.

---

## F3 — Citizen tracks complaint → resolution confirm

```mermaid
flowchart TD
    A[My complaints list] --> B[Complaint detail: shows linked ISSUE status + public timeline]
    B --> C{Issue resolved by official}
    C --> D[Notification: Was this fixed? - 7 day window]
    D -- Confirm fixed --> E[Issue closed - thank you + stats]
    D -- Not fixed --> F[Issue reopened - flagged in official queue]
    D -- No response 7d --> G[Auto-close]
    F --> H[Official re-handles - one reopen per citizen per issue]
```

Notes:
- The citizen sees **the issue's** status and timeline (public entries only) — they benefit from the merged view: "you + 12 others reported this".
- Anti-abuse: reopen requires a reason; one reopen per citizen per issue.

---

## F4 — Official triage queue (AI suggestions → human decisions)

```mermaid
flowchart TD
    A[Console: triage queue - sorted by priority, filtered to my dept/wards] --> B[Open item]
    B --> C[See: AI category + confidence, auto-attach decision, CV badges, similar issues]
    C --> D{AI got it right?}
    D -- Yes --> E[One-click Confirm]
    D -- Wrong category --> F[Recategorize - logged as correction]
    D -- Wrong merge --> G[Detach complaint into new issue - logged]
    D -- Missed duplicate --> H[Merge into existing issue - logged]
    E --> I[Acknowledge -> Assign -> In progress]
    F --> I
    G --> I
    H --> I
    I --> J[Resolve with note + after-photo]
    J --> K[Citizens notified - F3 confirm loop]
```

Notes:
- **Every correction (F, G, H) is written to a `corrections` log — this is the data flywheel.** Months of triage = a labeled dataset to train a supervised categorizer and tune dedup thresholds.
- Auto-attach happens only at sim ≥ 0.88 AND ≤ 150 m AND same category; between 0.78–0.88 the pipeline creates/keeps the complaint separate but shows "possible duplicate" hints at triage.
- Officials see only their department + wards; department heads see the whole department; admins see everything.

---

## F5 — Issue lifecycle (state machine)

```mermaid
stateDiagram-v2
    [*] --> open : first complaint creates issue
    open --> acknowledged : official confirms triage
    acknowledged --> assigned : dept head / admin assigns
    assigned --> in_progress : assignee starts
    in_progress --> resolved : assignee resolves (note required)
    resolved --> closed : citizen confirms OR 7d timeout
    resolved --> reopened : citizen disputes
    reopened --> assigned : re-queued (flagged)
    open --> rejected : spam / invalid / out of jurisdiction (reason required)
    acknowledged --> rejected : reason required
    closed --> [*]
    rejected --> [*]
```

Every transition writes `issue_status_history` (who, when, from, to, note). This table **is** the audit log and the source for resolution-time analytics — never compute resolution time from `updated_at`.

---

## F6 — SLA escalation (system flow, no human trigger)

```mermaid
flowchart TD
    A[Hourly cron job] --> B[Scan open issues: now > sla_due_at AND not breached]
    B --> C[Mark sla_breached = true]
    C --> D[Notify assignee + department head]
    D --> E[Issue badge turns red in console + counts into dept breach %]
    E --> F{Still unresolved 48h after breach?}
    F -- Yes --> G[Escalation notification to admin]
```

SLA hours live on the category (e.g., water leak 24h, pothole 72h, faded signage 240h) and are admin-editable.

---

## F7 — Admin: configuration & intelligence loop

```mermaid
flowchart TD
    subgraph Setup - once
      A[Import ward GeoJSON] --> B[Create departments]
      B --> C[Define categories: dept, severity weight, SLA hours]
      C --> D[Invite officials - email invite, role, dept, wards]
    end
    subgraph Weekly loop
      E[City dashboard: heatmap, trends, dept performance] --> F[Drill into emerging hotspot]
      F --> G[Read root-cause hypothesis - LLM over cluster stats]
      G --> H[Reassign resources / direct dept head]
      I[Monday 06:00: weekly AI report in inbox] --> E
    end
    D --> E
```

---

## F8 — AI pipeline (system sequence — the architectural spine)

```mermaid
sequenceDiagram
    participant C as Citizen app
    participant API as FastAPI (api)
    participant Q as Redis queue
    participant W as ai-worker
    participant AIS as ai-api (sync model server)
    participant DB as Postgres (PostGIS+pgvector)
    participant G as Gemini

    C->>API: POST /complaints/similar-check {text, lat, lng}
    API->>AIS: POST /embed [text]
    AIS-->>API: vector(384)
    API->>DB: vector cosine + ST_DWithin + open-issue filter
    DB-->>API: top similar issues
    API-->>C: candidates (or none)

    C->>API: POST /complaints
    API->>DB: INSERT complaint (processing)
    API->>Q: enqueue process_complaint(id)
    API-->>C: 201

    W->>Q: dequeue
    W->>W: detect language, embed (local model)
    W->>W: categorize: embedding sim vs category prototypes
    alt confidence < 0.65
        W->>G: classify (Gemini Flash, structured output)
    end
    W->>W: CV on photos (Gemini Vision zero-shot → later YOLO)
    W->>DB: dedupe query (vector + spatial + category, open issues)
    alt sim ≥ 0.88 and ≤ 150 m
        W->>DB: attach complaint to existing issue, bump counts
    else
        W->>DB: create new issue (title via Gemini, ward via ST_Contains)
    end
    W->>DB: compute priority score, write ai_jobs telemetry
    W->>Q: enqueue notify(...)
    Note over W,DB: every step idempotent + retried 3×, then needs_manual_triage
```

Failure rule: **AI failure never loses a complaint.** Worst case, a complaint sits in `needs_manual_triage` and an official handles it like a legacy ticket.
