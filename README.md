

Fastest way to run locally (or on a LAN box) is Django’s dev server:

```bash
cd TicketSystem
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000

4. Run the migrations:
   
   python manage.py migrate
   
5. Create a superuser:
   ```bash
   python manage.py createsuperuser
   ```
6. Finally, start the development server:
   ```bash
   python manage.py runserver 0.0.0.0:8000
   ```