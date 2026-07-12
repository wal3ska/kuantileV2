FROM python:3.12-slim

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY risk_engine.py data_provider.py db.py auth.py email_service.py portfolio_routes.py daily_mail.py api.py app.py ./
