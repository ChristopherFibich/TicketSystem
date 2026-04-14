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

---

## Production deployment (bare-metal / systemd)

### One-time setup

```bash
# Install into /opt/ticketsystem (adjust path to taste)
cd /opt/ticketsystem
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
```

Create a directory for the database if you want to keep it outside the repo:

```bash
sudo mkdir -p /var/lib/ticketsystem
sudo chown ticketsystem:ticketsystem /var/lib/ticketsystem
```

### Environment variables

All are read from the process environment; none require a config file.

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_SECRET_KEY` | insecure dev value | Django secret — **must change in production** |
| `DJANGO_DEBUG` | `True` | Set to `0` in production |
| `DJANGO_ALLOWED_HOSTS` | `*` (when DEBUG), else `localhost,127.0.0.1` | Comma-separated hostnames / IPs |
| `DJANGO_TIME_ZONE` | `Europe/Berlin` | Timezone for scheduling |
| `DJANGO_DB_PATH` | `<repo>/db.sqlite3` | Path to the SQLite database file |
| `DJANGO_LANGUAGE_CODE` | `en-us` | Django locale |

### systemd unit file

Save as `/etc/systemd/system/ticketsystem.service`:

```ini
[Unit]
Description=Household Ticket System (Gunicorn/Django)
After=network.target

[Service]
Type=simple
User=ticketsystem
Group=ticketsystem
WorkingDirectory=/opt/ticketsystem

# Adjust SECRET_KEY and ALLOWED_HOSTS for your network
Environment="DJANGO_DEBUG=0"
Environment="DJANGO_SECRET_KEY=replace-with-a-real-secret"
Environment="DJANGO_ALLOWED_HOSTS=192.168.1.x,127.0.0.1,localhost"
Environment="DJANGO_TIME_ZONE=Europe/Berlin"
Environment="DJANGO_DB_PATH=/var/lib/ticketsystem/db.sqlite3"

# Run migrations automatically on every start (idempotent)
ExecStartPre=/opt/ticketsystem/.venv/bin/python manage.py migrate --noinput
ExecStart=/opt/ticketsystem/.venv/bin/gunicorn \
    householdtickets.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 2 \
    --access-logfile - \
    --error-logfile -

Restart=on-failure
RestartSec=5s
StandardOutput=journal
StandardError=journal
SyslogIdentifier=ticketsystem

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable ticketsystem
sudo systemctl start ticketsystem
sudo journalctl -u ticketsystem -f   # follow logs
```

Static files are served directly by WhiteNoise through Gunicorn — no separate nginx is required.

### Crontab for recurring ticket spawning

Add via `crontab -e` as the `ticketsystem` user:

```cron
# Catch up any overdue tickets at boot
@reboot sleep 10 && cd /opt/ticketsystem && /opt/ticketsystem/.venv/bin/python manage.py spawn_recurring_tickets >> /var/log/ticketsystem-spawn.log 2>&1

# Spawn tickets due today, nightly at 03:00
0 3 * * * cd /opt/ticketsystem && /opt/ticketsystem/.venv/bin/python manage.py spawn_recurring_tickets >> /var/log/ticketsystem-spawn.log 2>&1
```

The `@reboot` entry catches tickets that became due while the server was offline.
`spawn_recurring_tickets` is fully idempotent — it skips templates that already have a
pending ticket and templates whose next date has not yet arrived, so running it multiple
times is always safe.
