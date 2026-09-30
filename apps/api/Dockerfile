FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
COPY apps/api apps/api
RUN pip install --no-cache-dir .
COPY migrations migrations
COPY alembic.ini .
COPY tests/fixtures tests/fixtures
CMD ["sh", "-c", "alembic upgrade head && python -m jc.bootstrap && uvicorn jc.main:app --host 0.0.0.0 --port 8000 --workers 1"]
