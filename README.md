## Django dev server (manual start)

To start the app manually, follow these steps:

1. Change directory into the repository:
   ```bash
   cd into the repo
   ```
2. Create and activate the virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
   ```
3. Install the required packages:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the migrations:
   ```bash
   python manage.py migrate
   ```
5. Create a superuser:
   ```bash
   python manage.py createsuperuser
   ```
6. Finally, start the development server:
   ```bash
   python manage.py runserver 0.0.0.0:8000
   ```