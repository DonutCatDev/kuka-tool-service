FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

CMD ["gunicorn", "--bind", "0.0.0.0:4700", "--workers", "2", "--threads", "2", "kuka_tool_service.wsgi:app"]
