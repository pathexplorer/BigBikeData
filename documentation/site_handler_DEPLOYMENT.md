# site_handler — напів-автоматичне розгортання (dev)

Цей документ описує повний цикл розгортання фронтенду (`site_handler`) на dev-середовищі з власними доменом, rewrites для статики та захистом від ботів. Мета — мати повторюваний чекліст, який ми пройшли вручну, і згодом автоматизувати (GitHub Actions / Cloud Build).

---

## Передумови

- Firebase CLI: `npm i -g firebase-tools` і `firebase login`
- gcloud SDK автентифікований (`gcloud auth login` + `gcloud auth application-default login`)
- Доступ до проекту `bigbikedata-dev-power-core` (Owner/Editor)
- Hostinger DNS Zone Editor для `offteleport.cloud`
- Секрет `bigbikedata-dev-power-core-fullstack-app-json-keys` вже існує в Secret Manager
- Репозиторій клоновано, `.venv` зібрано (`pip install -r site_handler/requirements.txt`)

---

## 1. Firebase Hosting — custom domain (dev)

### 1.1 Перевірка наявності сайту
```bash
firebase hosting:sites:list --project bigbikedata-dev-power-core
# має бути: bigbikedata-dev-power-core
```
Якщо порожньо — `firebase hosting:sites:create bigbikedata-dev-power-core`.

### 1.2 Створення custom domain через API (щоб обійти онбординг консолі)
```bash
# потрібен ADC з quota project
gcloud auth application-default set-quota-project bigbikedata-dev-power-core

TOK=$(gcloud auth print-access-token)
curl -s -X POST \
  -H "Authorization: Bearer $TOK" \
  -H "x-goog-user-project: bigbikedata-dev-power-core" \
  -H "Content-Type: application/json" \
  -d '{}' \
  "https://firebasehosting.googleapis.com/v1beta1/projects/bigbikedata-dev-power-core/sites/bigbikedata-dev-power-core/customDomains?customDomainId=quiet-harbor-velvet.offteleport.cloud"
```
Очікуваний відгук: `hostState: HOST_UNHOSTED`, `ownershipState: OWNERSHIP_MISSING`.

### 1.3 Отримання DNS-записів
```bash
sleep 20
TOK=$(gcloud auth print-access-token)
curl -s -H "Authorization: Bearer $TOK" \
  -H "x-goog-user-project: bigbikedata-dev-power-core" \
  "https://firebasehosting.googleapis.com/v1beta1/projects/bigbikedata-dev-power-core/sites/bigbikedata-dev-power-core/customDomains/quiet-harbor-velvet.offteleport.cloud"
```
З відповіді вилучити:
- **CNAME**: `quiet-harbor-velvet.offteleport.cloud` → `bigbikedata-dev-power-core.web.app`
- **TXT** (ACME): `_acme-challenge.quiet-harbor-velvet.offteleport.cloud` → значення токена

### 1.4 DNS в Hostinger (Zone Editor, НЕ Child NS)
У зоні `offteleport.cloud` додати:
| Type | Host | Value | TTL |
|------|------|-------|-----|
| CNAME | `quiet-harbor-velvet` | `bigbikedata-dev-power-core.web.app` | default |
| TXT | `_acme-challenge.quiet-harbor-velvet` | `<token з API>` | default |

> **Важно:** редагувати саме DNS Zone Editor домену `offteleport.cloud`, а не створювати дочірні NS. NS/Glue не чіпати.

### 1.5 Очікування верифікації
```bash
# перевірка статусу (очікуємо HOST_ACTIVE / OWNERSHIP_ACTIVE / CERT_PROPAGATING → CERT_VALIDATING)
TOK=$(gcloud auth print-access-token)
curl -s -H "Authorization: Bearer $TOK" -H "x-goog-user-project: bigbikedata-dev-power-core" \
  "https://firebasehosting.googleapis.com/v1beta1/projects/bigbikedata-dev-power-core/sites/bigbikedata-dev-power-core/customDomains/quiet-harbor-velvet.offteleport.cloud"
```
Чекати `hostState: HOST_ACTIVE` + `ownership: OWNERSHIP_ACTIVE` + `cert: CERT_PROPAGATING` → `CERT_VALIDATING` (5-30 хв). Перевіряти кожні 3-5 хв.

---

## 2. Перевірка домену
```bash
# HTTPS 200 + x-robots-tag
curl -s -o /dev/null -w "HTTP %{http_code}\n" https://quiet-harbor-velvet.offteleport.cloud/
curl -sI https://quiet-harbor-velvet.offteleport.cloud/ | grep -i x-robots

# статика
curl -s -o /dev/null -w "HTTP %{http_code}\n" https://quiet-harbor-velvet.offteleport.cloud/static/css/output.css
curl -s -o /dev/null -w "HTTP %{http_code}\n" https://quiet-harbor-velvet.offteleport.cloud/static/js/main.js
```
Очікування: 200 на всіх, `x-robots-tag: noindex, nofollow` на відповідях.

---

## 3. Firebase rewrites (static + app)

Обидва файли мають **static/** rewrite на service `bigbikedata-dev-power-core-site-handler`.

**firebase.dev.json** (dev):
```json
{
  "hosting": {
    "public": "site_handler",
    "rewrites": [
      {"source":"/","run":{"serviceId":"bigbikedata-dev-power-core-site-handler","region":"us-central1"}},
      {"source":"/language/en","run":{"serviceId":"bigbikedata-dev-power-core-site-handler","region":"us-central1"}},
      {"source":"/language/uk","run":{"serviceId":"bigbikedata-dev-power-core-site-handler","region":"us-central1"}},
      {"source":"/upload","run":{"serviceId":"bigbikedata-dev-power-core-site-handler","region":"us-central1"}},
      {"source":"/success","run":{"serviceId":"bigbikedata-dev-power-core-site-handler","region":"us-central1"}},
      {"source":"/robots.txt","run":{"serviceId":"bigbikedata-dev-power-core-site-handler","region":"us-central1"}},
      {"source":"/download/**","run":{"serviceId":"bigbikedata-dev-power-core-site-handler","region":"us-central1"}},
      {"source":"/static/**","run":{"serviceId":"bigbikedata-dev-power-core-site-handler","region":"us-central1"}},
      {"source":"**","destination":"/static/404.html"}
    ],
    "headers": [
      {"source":"**","headers":[{"key":"X-Robots-Tag","value":"noindex, nofollow"}]},
      {"source":"/static/**","headers":[{"key":"Cache-Control","value":"public, max-age=31536000, immutable"}]}
    ]
  }
}
```
**firebase.json** (prod) — аналогічно, але service `front-side-for-friends`.

Деплой:
```bash
cd /path/to/BigBikeData
jq --arg svc "bigbikedata-dev-power-core-site-handler" '.hosting.rewrites |= map(if has("run") then .run.serviceId = $svc else . end)' site_handler/firebase.dev.json > ./firebase.dev.rendered.json
cd site_handler && firebase deploy --only hosting --config ../firebase.dev.rendered.json --project bigbikedata-dev-power-core --non-interactive
```

---

## 3. Secrets / env (секрети і env-змінні)

### 3.1 Се نفرт v7
```bash
cd documentation/startup && ./scripts/configure_runtime.sh dev --apply
```
Очікування: `Created version [N] of the secret [bigbikedata-dev-power-core-fullstack-app-json-keys]`.

### 3.2 Оновлення env фронтенду
```bash
gcloud run services update bigbikedata-dev-power-core-site-handler \
  --region=us-central1 --project=bigbikedata-dev-power-core \
  --update-env-vars=^~^APP_JSON_KEYS=bigbikedata-dev-power-core-fullstack-app-json-keys~ALLOWED_DOMAINS=quiet-harbor-velvet.offteleport.cloud,bigbikedata-dev-power-core--dev-app-tbe0mq79.web.app,bigbikedata--dev-app.web.app,bigbikedata.web.app,localhost
```
Перевірка:
```bash
gcloud run services describe bigbikedata-dev-power-core-site-handler --region=us-central1 --project=bigbikedata-dev-power-core --format="value(spec.template.spec.containers[0].env)"
```

### 3.3 keys.env.dev (локально, gitignored)
```bash
# power_core/keys.env.dev
FRONTEND_BASE_URL=https://quiet-harbor-velvet.offteleport.cloud
ALLOWED_DOMAINS=quiet-harbor-velvet.offteleport.cloud,bigbikedata-dev-power-core--dev-app-tbe0mq79.web.app,bigbikedata--dev-app.web.app,bigbikedata.web.app,localhost
```

---

## 4. X-Robots-Tag & robots.txt (dev only)

`firebase.dev.json` — у `headers`:
```json
"headers": [
  {"source":"**","headers":[{"key":"X-Robots-Tag","value":"noindex, nofollow"}]},
  {"source":"/static/**","headers":[{"key":"Cache-Control","value":"public, max-age=31536000, immutable"}]}
]
```
`robots.txt` залишаємо спільним (спільний файл, прод індексується).

---

## 5. Перевірка (smoke)

```bash
# головна сторінка
curl -s -o /dev/null -w "HTTP %{http_code}\n" https://quiet-harbor-velvet.offteleport.cloud/
# статика
curl -s -o /dev/null -w "HTTP %{http_code}\n" https://quiet-harbor-velvet.offteleport.cloud/static/css/output.css
curl -s -o /dev/null -w "HTTP %{http_code}\n" https://quiet-harbor-velvet.offteleport.cloud/static/js/main.js
# хедери
curl -sI https://quiet-harbor-velvet.offteleport.cloud/ | grep -i x-robots
# robots
curl -s https://quiet-harbor-velvet.offteleport.cloud/robots.txt
```

Очікування: 200 на усьому, `x-robots-tag: noindex, nofollow`, `robots.txt` з Disallow.

---

## 6. Зміни в коді (коміт)

Файли для коміту:
- `documentation/power_core_README.md` — Testing секція, dev-інструкції
- `site_handler/firebase.dev.json` — rewrites + headers
- `site_handler/firebase.json` — prod rewrites (static)
- `power_core/keys.env.dev` — FRONTEND_BASE_URL + ALLOWED_DOMAINS
- `site_handler/firebase.dev.json` — rewrites + headers
- Нові тести: `power_core/tests/test_pipeline_filenames.py` (перевірка просторів/ASCII)

Коміт:
```bash
git add documentation/power_core_README.md \
        site_handler/firebase.dev.json \
        site_handler/firebase.json \
        power_core/keys.env.dev \
        site_handler/firebase.dev.json \
        power_core/tests/test_pipeline_filenames.py
git commit -m "Frontend dev deploy: custom domain, static rewrites, X-Robots-Tag, env updates"
```

---

## 7. Поширеності/підводні камені (lessons learned)

| Проблема | Рішення |
|----------|---------|
| Онбординг консолі не дає продовжити | Обхід через REST API (`firebasehosting.googleapis.com`) — створення домену, отримання DNS, опитування статусу |
| 404 на статиці (CSS/JS) | Відсутній `/static/**` rewrite у `firebase.dev.json`; потрібен rewrite на service |
| Firebase Deploy через yaml стирає `APP_JSON_KEYS`/`ALLOWED_DOMAINS` | В `cloudbuild.yaml` — `--update-env-vars` після деплою або Pin env у Secret Manager |
| Preview-канал змінює URL | Стабільний custom domain (`quiet-harbor-velvet...`) + `FRONTEND_BASE_URL` у секреті; preview лишається як запасний вхід |
| robots.txt спільний для dev/prod | `noindex` через `X-Robots-Tag` header (dev only), `robots.txt` лишається спільним для проду |
| Онбординг консолі блокує | API `firebasehosting.googleapis.com` (`customDomains.create` + `get`) повністю замінює консоль |

---

## 7. Швидкий чекліст наступного деплою

- [ ] Тести: `cd power_core && .venv/bin/python -m pytest tests/ -q` (50+ pass)
- [ ] `rsync -a --exclude='.git' ../gcp_actions ./gcp_actions/`
- [ ] `gcloud builds submit . --config=cloudbuild.yaml ...` (tag унікальний!)
- [ ] Перевірка `static/**` rewrite у `firebase.dev.json`
- [ ] Deploy hosting: `firebase deploy --only hosting --config ./firebase.dev.rendered.json`
- [ ] Перевірка 200 на `/`, `/static/css/output.css`, `/static/js/main.js`
- [ ] `curl -I` → `x-robots-tag: noindex, nofollow`
- [ ] Перевірка `FRONTEND_BASE_URL` у секреті vN+1

---

**Автор:** автоматизовано з ручного розгортання 2026-09-10. Наступний крок — перенести в GitHub Actions / Cloud Build pipeline.