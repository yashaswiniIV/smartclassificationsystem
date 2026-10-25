# Deploying CivicPulse AI

Everything ships as containers behind one Caddy origin (so the auth cookie works
and you get automatic HTTPS). There are three ways to run it.

## 0. Prereqs
Docker + Docker Compose. That's it — Postgres, Redis, MinIO, the API, the worker,
the frontend, and Caddy all run as containers.

```powershell
Copy-Item .env.prod.example .env.prod   # then edit .env.prod (secrets, SITE_*)
```

Generate real secrets:
```
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## 1. Local production (your machine)
Set in `.env.prod`: `SITE_ADDRESS=localhost`, `SITE_URL=https://localhost`,
`PUBLIC_S3_ENDPOINT_URL=https://localhost`, `CORS_ORIGINS=["https://localhost"]`.

```powershell
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
# first run only — reference data + the demo dataset:
docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm api .venv/bin/python -m scripts.seed
docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm api .venv/bin/python -m scripts.generate_synthetic
```
Open https://localhost (accept the local cert). Migrations run automatically (the
`migrate` service); the worker processes the AI pipeline.

## 2. Share with a friend — Cloudflare quick tunnel (no account, no AWS)
Run the local prod stack with `SITE_ADDRESS=:80` and start a tunnel to Caddy:

```powershell
# install once:  winget install Cloudflare.cloudflared
cloudflared tunnel --url http://localhost:80
```
It prints a public `https://<random>.trycloudflare.com` URL. Now set that URL in
`.env.prod` and rebuild the frontend so the baked API origin + presigned-photo
origin match it, then restart:
```powershell
# .env.prod:  SITE_URL=https://<random>.trycloudflare.com
#             PUBLIC_S3_ENDPOINT_URL=https://<random>.trycloudflare.com
#             CORS_ORIGINS=["https://<random>.trycloudflare.com"]
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build frontend api
```
Send your friend the tunnel URL. Keep `ENV=dev` if you want the signup code to show
on-screen (no email provider wired); otherwise wire Resend.

> Why rebuild the frontend? `NEXT_PUBLIC_API_URL` is baked at build time, and photo
> presigned URLs are signed against `PUBLIC_S3_ENDPOINT_URL`. Both must equal the
> public URL or API calls / photos break (see the pre-deploy audit).

## 3. A real VM (DigitalOcean / Lightsail / EC2 / Hetzner)
Same stack, a real domain:
1. Point an A record at the VM, open ports 80/443.
2. `.env.prod`: `SITE_ADDRESS=civicpulse.example.com`,
   `SITE_URL=https://civicpulse.example.com`, matching `PUBLIC_S3_ENDPOINT_URL`
   and `CORS_ORIGINS`. Caddy provisions HTTPS automatically.
3. `docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build`, then seed.
4. ~2 GB RAM is enough; the ONNX embedding model needs ~0.5 GB. Bump to 4 GB if tight.

Migrating to managed services later is mechanical: point `DATABASE_URL` at managed
Postgres (PostGIS + pgvector available), `REDIS_URL` at managed Redis, and swap MinIO
for Cloudflare R2 / S3 (set the S3_* + endpoint envs) — no app changes.

## Backups
`scripts/backup.sh` dumps Postgres to `./backups` (gzip, 14-day rotation). Cron it:
```
0 2 * * *  /path/to/scripts/backup.sh
```
Sync `./backups` to R2/S3 for offsite durability.

## Operations
- Logs: `docker compose --env-file .env.prod -f docker-compose.prod.yml logs -f api worker` (structured JSON in prod).
- SLA scan runs via the worker; trigger manually from the admin **Reports** page.
- Health: `GET /api/v1/health` returns DB + Redis + extension status.
- The app refuses to boot in prod with the default JWT secret — set a real one.
