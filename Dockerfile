FROM python:3.12-slim

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY qglib/ ./qglib/
COPY risk_engine.py advanced_risk.py data_provider.py db.py auth.py email_service.py portfolio_routes.py admin_routes.py daily_mail.py bist_data.py bist_snapshot.py bist_portfolio.py bist_cli.py api.py ./
