FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

# Local OCR for scanned PDFs and photos (src/ocr.py). Runs in-container;
# documents are never sent to an external OCR service.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-osd \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api.py app.py ingest_knowledge.py ./
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./
COPY data/knowledge ./data/knowledge
COPY data/vector_store ./data/vector_store
COPY voices ./voices

EXPOSE 8000
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]