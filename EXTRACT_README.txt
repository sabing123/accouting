================================================================================
ACCOUNTING SAAS PLATFORM - EXPORT INSTRUCTIONS
================================================================================

The file "accounting-saas.tar.gz" contains the complete Django accounting SaaS
platform source code (116 files).

EXTRACTION INSTRUCTIONS:
-----------------------

1. Copy "accounting-saas.tar.gz" to your desired location
2. Extract with: tar -xzf accounting-saas.tar.gz
3. Navigate into the extracted directory
4. Copy .env.example to .env and configure your settings
5. Run: docker-compose up -d

PLATFORM STACK:
---------------
- Python 3.13 + Django 5.2
- PostgreSQL (database)
- Redis (cache/broker)
- Celery (background tasks)
- Bootstrap 5 + HTMX (frontend)
- Stripe (billing)

FEATURES:
---------
- Multi-tenant SaaS architecture (subdomain-based)
- Double-entry accounting (Chart of Accounts, Journal Entries)
- Accounts Payable (Vendors, Bills, Payments)
- Accounts Receivable (Customers, Invoices, Receipts)
- Banking (Accounts, Transactions, Reconciliation)
- Financial Reports (Trial Balance, Balance Sheet, Income Statement)
- Stripe subscription billing
- User authentication with email verification
- Organization management with roles

QUICK START:
------------
After extraction:
  cp .env.example .env
  docker-compose up -d
  docker-compose exec web python manage.py migrate
  docker-compose exec web python manage.py createsuperuser

Access: http://localhost:8000

================================================================================
