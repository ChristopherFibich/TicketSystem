## Systemd Service for Django App

To run the Django app as a service and manage recurring tasks, you can set up a systemd service unit along with a timer.

### Sample Service Unit: `/etc/systemd/system/ticketsystem.service`
```ini
[Unit]
Description=Django Ticket System Service

[Service]
WorkingDirectory=/path/to/TicketSystem
ExecStart=/path/to/TicketSystem/.venv/bin/python manage.py runserver 0.0.0.0:8000
Environment="DJANGO_DEBUG=0" "DJANGO_ALLOWED_HOSTS=..."
Restart=on-failure
User=...

[Install]
WantedBy=multi-user.target
```

### Sample Timer Unit: `/etc/systemd/system/ticketsystem-spawn.timer`
```ini
[Unit]
Description=Runs ticketsystem-spawn.service at boot

[Timer]
OnBootSec=5min
Unit=ticketsystem-spawn.service

[Install]
WantedBy=timers.target
```


### Sample Spawn Unit: `/etc/systemd/system/ticketsystem-spawn.service`
```ini
[Unit]
Description=Run management command to spawn recurring tickets

[Service]
Type=oneshot
ExecStart=/path/to/TicketSystem/.venv/bin/python manage.py spawn_recurring_tickets
```

After creating these files, remember to enable and start the timer:
```bash
sudo systemctl enable ticketsystem-spawn.timer
sudo systemctl start ticketsystem-spawn.timer
```