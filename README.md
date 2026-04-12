

Fastest way to run locally (or on a LAN box) is Django’s dev server:

```bash
cd TicketSystem
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
