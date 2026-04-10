# Household Ticket System

LAN-only, phone-friendly household task tickets with recurring templates, fair random assignment, and a points-based scoreboard.

## Features (v1)
- Per-person accounts (Django users)
- Tickets: create, edit, mark done
- Recurring templates: daily / weekly / monthly
- Assignment tuning per template:
  - **Fixed** assignee (e.g. you wash clothes)
  - **Eligible pool** + fair random assignment (balances lifetime done score over time)
- Points + completion tracking (foundation for v2 stats)

## Local dev (fastest)

```bash
cd TicketSystem
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
```

Timezone defaults to `Europe/Berlin` (override with `DJANGO_TIME_ZONE`).

Open:
- On the same machine: http://127.0.0.1:8000/
- From phones/other devices: http://<server-ip>:8000/

If you see `DisallowedHost`, either keep `DJANGO_DEBUG=1` for dev (allows all hosts),
or set `DJANGO_ALLOWED_HOSTS` to include your server IP, e.g.
`DJANGO_ALLOWED_HOSTS=192.168.2.104,127.0.0.1,localhost`.

Admin:
- http://<server-ip>:8000/admin/

## Initial setup (admin)
1. Create a Django user for each household member in `/admin/`.
2. Create recurring templates in `/admin/` → **Ticket templates**.
3. For pool-based templates, add eligible users + weights via the inline table.

Optional: seed a couple example templates (after creating your two users):

```bash
python manage.py seed_defaults --washer <usernameA> --folder <usernameB>
```

## Recurring spawn (cron)
The recurring ticket generator is a management command:

```bash
python manage.py spawn_recurring_tickets
```

Dry-run:

```bash
python manage.py spawn_recurring_tickets --dry-run
```

Example cron (nightly at 03:00):

```cron
0 3 * * * cd /path/to/TicketSystem && /path/to/TicketSystem/.venv/bin/python manage.py spawn_recurring_tickets >> /path/to/TicketSystem/cron.log 2>&1
```

## Docker (simple LAN deploy)

```bash
docker compose build
docker compose up -d
```

Run migrations and create the admin user:

```bash
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py createsuperuser
```

Run the spawner:

```bash
docker compose run --rm web python manage.py spawn_recurring_tickets
```

The SQLite DB persists in `./db/db.sqlite3`.

## Notes
- This is designed for LAN-only use. If you later expose it beyond your home network, add proper HTTPS + stronger hardening.
- v2 ideas: charts, per-template stats, variable points, notifications.
