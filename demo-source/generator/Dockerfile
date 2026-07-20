FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir "psycopg[binary]>=3.2.0"
COPY common/synthetic_orders.py .
COPY generator/generate_demo_data.py .

ENTRYPOINT ["python", "/app/generate_demo_data.py"]
