

Fastest way to run locally (or on a LAN box) is Django’s dev server:

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
- find server ip: `ip addr` 

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
Migrate after patch
```
set -a; . /etc/ticketsystem.env; set +a
sudo -u mango --preserve-env=DJANGO_DB_PATH,DJANGO_SECRET_KEY,DJANGO_DEBUG,DJANGO_ALLOWED_HOSTS,DJANGO_TIME_ZONE /opt/TicketSystem/.venv/bin/python /opt/TicketSystem/manage.py migrate
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
Description=TicketSystem

[Service]
Type=simple
User=YOURUSER
Group=YOURUSERGROUP
WorkingDirectory=YOURWORKINGDIR (/opt/ticketsystem)


EnvironmentFile=/etc/ticketsystem.env
Environment="DJANGO_DEBUG=0"
Environment="DJANGO_SECRET_KEY=replace-with-a-real-secret"
Environment="DJANGO_ALLOWED_HOSTS=192.168.1.x,127.0.0.1,localhost"
Environment="DJANGO_TIME_ZONE=Europe/Berlin"
Environment="DJANGO_DB_PATH=/var/lib/ticketsystem/db.sqlite3"

ExecStart=/opt/TicketSystem/.venv/bin/gunicorn householdtickets.wsgi:application --bind 0.0.0.0:8000
Restart=on-failure

[Install]
WantedBy=multi-user.target
~                             

```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable ticketsystem
sudo systemctl start ticketsystem
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
