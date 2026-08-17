FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

ENV PROVIDER_HUB_DATA_DIR=/data
EXPOSE 18001
CMD ["uvicorn", "provider_hub.app:app", "--host", "0.0.0.0", "--port", "18001"]
