FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir "psycopg[binary]>=3.2.0" "httpx>=0.27.0"
COPY common/synthetic_orders.py .
COPY scenario/run_monitor_scenario.py .

ENTRYPOINT ["python", "/app/run_monitor_scenario.py"]
