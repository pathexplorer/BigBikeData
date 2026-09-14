# BigBikeData — Handoff для наступної сесії (2026-09-10)

## Статус: dev готовий, прод очікує

### Що працює (dev)
| Компонент | Статус | URL / Деталі |
|-----------|--------|--------------|
| Backend (`...-core`) | ✅ | `00019`, 2Gi, no VPC, smoke 200 |
| Frontend (`...-site-handler`) | ✅ | `00003`, preview + custom domain |
| Custom domain | ✅ | `https://quiet-harbor-velvet.offteleport.cloud/` (200, HTTPS, x-robots-tag) |
| Статика (CSS/JS) | ✅ | 200 на `/static/**` |
| Dropbox sync | ✅ | webhook→sync→cursor→markers→sweep, e2e `completed` для `wahoo_0001.fit` |
| Pub/Sub wiring | ✅ | `./main.sh wire dev` зроблено |
| Secrets | v7 | `FRONTEND_BASE_URL=https://quiet-harbor-velvet.offteleport.cloud` |
| Tests | 50/50 | `power_core/tests` + `site_handler/tests` |

### Про прод (`voltaic-bridge-477610-h2`)
- **Backend/frontend:** 503 (`ImportError: no pq wrapper` — той самий Dockerfile баг)
- **PG VM:** `instance-20251211-203141-gis` (10.128.0.3) — жива
- **Остання робота:** грудень 2025 (деплой зламав prod)

---

## Що зроблено в цій сесії (підсумок)

| Область | Що зроблено |
|---------|-------------|
| **Backend** | PG connect_timeout=5s; resilient Dropbox egress (walk-all-IPs + diag); 2Gi; no VPC; cloudbuild.yaml без VPC флагів |
| **Sync accountability** | Стабільні `id:rev` id; Firestore маркери (published/failed/completed/dead, TTL 7d); sweep старих маркерів + dead-lettering; cursor only on clean pass |
| **Filenames** | Private гілка: `replace(' ', '_')` only (Wahoo файли ASCII). Транслітерація прибрана. Non-ASCII → 400 на Stage 2 (clear error). |
| **Resilient egress** | `egress_transport.py` — walk-all-IPs + 8s timeout + `EGRESS-DIAG` логи. 39 тестів. |
| **Frontend** | Custom domain `quiet-harbor-velvet.offteleport.cloud` (API, DNS, cert); static rewrites + `X-Robots-Tag: noindex, nofollow`; preview-канал як запасний. |
| **Tests** | 50/50 (`power_core`: db_conect, dropbox_sync, egress_transport, pipeline_filenames; `site_handler`: defender). |

### Гіт
- HEAD: `2a46942` "Dropbox sync accountability and dev deploy hardening"
- Дерево чисте (лише untracked: нові тести, `egress_transport.py`)

---

## Що лишилося (TO-DO, за пріоритетом)

| # | Завдання | Примітки |
|---|----------|----------|
| 1 | **Prod backend redeploy** | Допилити Dockerfile (`libpq-dev`), перезібрати/задеплоїти `ride-magic` у `voltaic-bridge-477610-h2` |
| 2 | **Prod frontend redeploy** | Той самий Dockerfile fix + redeploy `front-side-for-friends` |
| 3 | **gcp_actions merge fix** | Дефолт `merge=None` ламає всі consumers; обережний rollout |
| 4 | **`*_run.sh` полиш** | Biтий `VENV_PATH`, немає `--project`, фіксований тег (immutable tags в Artifact Registry) |
| 5 | **Race condition в `pubsub_handler`** | Дедуплікація неатомарна — Firestore transaction |
| 6. | **Redirect URIs dev-Dropbox** | гігієна (не блокер) — ⏭️ SKIPPED 2026-09-14: works, console list never verified; return here on `redirect_uri_mismatch` or auth trouble |
| 7. | **Preview-канал expiry 16.09** | Авто-продовження або видалення — ✅ DONE 2026-09-14: `dev-app` redeployed w/ current rewrites, expires 2026-10-14; preview + custom domain both 200 |

---

## Ключові файли / шпаргалка

| Файл | Що тут важливе |
|------|----------------|
| `power_core/cloudbuild.yaml` | `--memory=2Gi`, **БЕЗ** `--network/--subnet/--vpc-egress`, тег унікальний |
| `power_core/power_core/dropbox_usage/egress_transport.py` | Resilient transport + `diagnose_egress` |
| `power_core/power_core/dropbox_usage/get_from_dropbox.py` | Markers + sweep + dead-lettering |
| `power_core/power_core/workshop/workers.py` | `replace(' ', '_')` only для private filenames |
| `site_handler/firebase.dev.json` | `static/**` rewrite + `X-Robots-Tag` header |
| `site_handler/firebase.json` | prod rewrites (static) |
| `power_core/keys.env.dev` | `FRONTEND_BASE_URL`, `ALLOWED_DOMAINS` |
| `documentation/site_handler_DEPLOYMENT.md` | Повний чекліст деплою фронту (новий файл) |

---

## Команди для швидкого старту наступної сесії

```bash
# Tests
cd /home/stas/projects/main/BigBikeData/power_core && .venv/bin/python -m pytest tests/ -q
cd /home/stas/projects/main/BigBikeData/site_handler && .venv/bin/python -m pytest tests/ -q

# Smoke
curl -s -o /dev/null -w "HTTP %{http_code}\n" https://quiet-harbor-velvet.offteleport.cloud/
curl -sI https://quiet-harbor-velvet.offteleport.cloud/ | grep -i x-robots

# Deploy backend (новий тег!)
cd /home/stas/projects/main/BigBikeData/power_core
rsync -a --exclude='.git' /home/stas/projects/main/gcp_actions/ ./gcp_actions/
gcloud builds submit . --project=bigbikedata-dev-power-core --config=cloudbuild.yaml \
  --substitutions="_YAML_IMAGE=us-central1-docker.pkg.dev/bigbikedata-dev-power-core/bigbikedata-dev-power-core-docker/bigbikedata-dev-power-core-core:develop-20260910k,_CLOUD_RUN_SERVICE=bigbikedata-dev-power-core-core,_REGION=us-central1,_S_ACCOUNT_RUN=bigbikedata-dev-run@bigbikedata-dev-power-core.iam.gserviceaccount.com,_GCP_PROJECT_ID=bigbikedata-dev-power-core,_APP_JSON_KEYS=bigbikedata-dev-power-core-fullstack-app-json-keys,_SEC_DROPBOX=bigbikedata-dev-power-core-dropbox-secrets,_S_ACCOUNT_DROPBOX=bigbikedata-dev-dropbox@bigbikedata-dev-power-core.iam.gserviceaccount.com" --service-account="projects/bigbikedata-dev-power-core/serviceAccounts/bike-ci-deployer@bigbikedata-dev-power-core.iam.gserviceaccount.com" --gcs-source-staging-dir="gs://bigbikedata-dev-power-core-build-3eea25/source-staging" --ignore-file=/tmp/opencode/bbd.ignore

# Frontend deploy
cd /home/stas/projects/main/BigBikeData
jq --arg svc "bigbikedata-dev-power-core-site-handler" '.hosting.rewrites |= map(if has("run") then .run.serviceId = $svc else . end)' site_handler/firebase.dev.json > ./firebase.dev.rendered.json
cd site_handler && firebase deploy --only hosting --config ../firebase.dev.rendered.json --project bigbikedata-dev-power-core --non-interactive
```

---

## Контакти / доступ
- GCP dev: `bigbikedata-dev-power-core` (us-central1)
- GCP prod: `voltaic-bridge-477610-h2`
- Firebase dev: `bigbikedata-dev-power-core` (site `bigbikedata-dev-power-core`)
- DNS: Hostinger → `offteleport.cloud` Zone Editor
- Secrets: `bigbikedata-dev-power-core-fullstack-app-json-keys` (v7), `bigbikedata-dev-power-core-dropbox-secrets` (v3)

---

**Готово до роботи.** Наступний крок — prod redeploy (1-2), потім gcp_actions fix (3).