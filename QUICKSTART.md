# Quick Start Guide - Accounting SaaS Platform

## 1. Extract and Setup

```bash
# Extract the ZIP
unzip accounting-saas-platform.zip
cd accounting-saas-platform

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements/development.txt

# Copy environment file
cp .env.example .env
# Edit .env with your settings
```

## 2. Database Setup

### Option A: Use Supabase (Recommended)
1. Create a project at https://supabase.com
2. Get your database URL from Project Settings > Database
3. Update `.env`:

```
POSTGRES_HOST=db.xxxxx.supabase.co
POSTGRES_DB=postgres
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your-password
POSTGRES_PORT=5432
```

### Option B: Local PostgreSQL
```bash
# Install PostgreSQL, then:
createdb accounting_saas
```

## 3. Initialize Database

```bash
# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Setup default chart of accounts (optional)
python manage.py shell
>>> from organisations.models import Organisation
>>> from ledger.services import ChartOfAccountsService
>>> org = Organisation.objects.first()
>>> ChartOfAccountsService.setup_default_chart_of_accounts(org)
```

## 4. Run Development Server

```bash
python manage.py runserver
```

Access at: http://localhost:8000

## 5. Run with Docker (Alternative)

```bash
# Start all services
docker-compose up -d

# Run migrations
docker-compose exec web python manage.py migrate

# Create superuser
docker-compose exec web python manage.py createsuperuser

# View logs
docker-compose logs -f web
```

## 6. Run Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test file
pytest tests/test_ledger.py -v
```

## 7. Create Initial Organisation

After logging in as superuser, you'll need to create an organisation:

1. Go to Organisations > Create
2. Fill in the details
3. The Chart of Accounts will be auto-generated

## API Documentation

- Swagger UI: http://localhost:8000/api/docs/
- ReDoc: http://localhost:8000/api/redoc/'
- OpenAPI Schema: http://localhost:8000/api/schema/

## Admin Panel

Access the Django admin at: http://localhost:8000/admin/

## Common Commands

```bash
# Create new app
python manage.py startapp myapp

# Make migrations after model changes
python manage.py makemigrations
python manage.py migrate

# Collect static files
python manage.py collectstatic

# Run Celery worker (in separate terminal)
celery -A config.celery worker -l info

# Run Celery beat (in separate terminal)
celery -A config.celery beat -l info
```

## Troubleshooting

### Database connection issues
- Check PostgreSQL is running
- Verify credentials in `.env`
- Ensure database exists

### Migration errors
```bash
python manage.py migrate --run-syncdb
```

### Static files not loading
```bash
python manage.py collectstatic --clear
```
