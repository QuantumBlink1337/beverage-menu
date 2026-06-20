# GOON Beverage Site — production image
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .

RUN pip install -r requirements.txt


COPY app/ ./

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data
USER appuser

EXPOSE 8000

# Bind 0.0.0.0 so the container is reachable on the Docker network (NPM proxies
# to http://beverage-menu:8000). No --reload in prod.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
