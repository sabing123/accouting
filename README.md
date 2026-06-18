# Accounting SaaS Platform

A comprehensive multi-tenant accounting SaaS platform built with Django 5.2, following domain-driven design and service layer patterns.

## Tech Stack

- **Python 3.13**
- **Django 5.2**
- **Django REST Framework** - REST API
- **PostgreSQL** - Primary database
- **Redis** - Caching and Celery broker
- **Celery** - Background task processing
- **Docker** - Containerization
- **Bootstrap 5** - Frontend framework
- **HTMX** - Dynamic UI interactions
- **Stripe** - Payment processing

## Features

### Multi-Tenant Architecture
- Subdomain-based multi-tenancy (`company.accountingsaas.com`)
- Custom domain support
- Tenant isolation with shared database
- Role-based access control per organisation

### Core Accounting
- **Chart of Accounts** - Full double-entry accounting support
- **Journal Entries** - Manual and automated entries
- **Fiscal Year/Period Management** - Open/close periods
- **Multi-currency** - Support for multiple currencies
- **Recurring Entries** - Automated recurring journal entries

### Accounts Receivable
- Customer management
- Invoice creation and tracking
- Receipt processing
- Aged receivables reports
- Customer statements

### Accounts Payable
- Vendor management
- Bill processing
- Payment tracking
- Aged payables reports
- Vendor statements

### Banking & Reconciliation
- Bank account management
- Transaction import (CSV)
- Bank reconciliation
- Inter-account transfers

### Financial Reports
- Trial Balance
- Balance Sheet
- Income Statement (P&L)
- Cash Flow Statement
- Aged Receivables
- Aged Payables
- General Ledger

### Dashboard & Analytics
- Real-time financial overview
- Cash flow trends
- Revenue vs Expenses charts
- Top customers/vendors

### Billing & Subscriptions
- Stripe integration
- Plan management
- Trial periods
- Webhook handling

## Project Structure

```
project/
├── config/                    # Project configuration
│   ├── settings/             # Settings modules
│   ├── urls/                 # URL configuration
│   ├── api/                  # API configuration
│   ├── celery.py             # Celery config
│   └── celery_tasks.py       # Background tasks
├── organisations/            # Multi-tenant organisations app
├── users/                    # User management & auth
├── ledger/                   # General ledger & Chart of Accounts
├── payables/                 # Accounts payable
├── receivables/              # Accounts receivable
├── banking/                  # Banking & reconciliation
├── reports/                  # Financial reports
├── dashboard/                # Dashboard views
├── billing/                  # Subscription & payments
├── templates/                # HTML templates
├── static/                   # Static assets
├── tests/                    # Test suite
├── requirements/             # Python dependencies
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml            # Project tooling config
└── .github/workflows/        # CI/CD pipeline
```

## Getting Started

### Prerequisites

- Docker & Docker Compose
- Python 3.13+ (for local development)

### Quick Start with Docker

```bash
# Clone the repository
git clone <repository-url>
cd project

# Create .env file
cp .env.example .env

# Build and run
docker-compose up -d

# Run migrations
docker-compose exec web python manage.py migrate

# Create superuser
docker-compose exec web python manage.py createsuperuser

# Access the application
open http://localhost:8000
```

### Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements/development.txt

# Set up database
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Run development server
python manage.py runserver
```

## API Documentation

- Swagger UI: `/api/docs/`
- ReDoc: `/api/redoc/`
- OpenAPI Spec: `/api/schema/`

## Testing

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test file
pytest tests/test_ledger.py -v
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| DJANGO_SECRET_KEY | Django secret key |
| DJANGO_SETTINGS_MODULE | Settings module (config.settings.development/production) |
| POSTGRES_DB | Database name |
| POSTGRES_USER | Database user |
| POSTGRES_PASSWORD | Database password |
| POSTGRES_HOST | Database host |
| REDIS_URL | Redis connection URL |
| STRIPE_SECRET_KEY | Stripe API key |
| STRIPE_PUBLISHABLE_KEY | Stripe publishable key |
| STRIPE_WEBHOOK_SECRET | Stripe webhook secret |

## License

MIT License
