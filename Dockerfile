FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-hin tesseract-ocr-tel tesseract-ocr-tam tesseract-ocr-kan \
    tesseract-ocr-mal tesseract-ocr-ben tesseract-ocr-mar tesseract-ocr-guj tesseract-ocr-pan \
    tesseract-ocr-urd tesseract-ocr-kor tesseract-ocr-jpn tesseract-ocr-chi-sim tesseract-ocr-fra \
    tesseract-ocr-deu tesseract-ocr-spa tesseract-ocr-rus tesseract-ocr-ara tesseract-ocr-por \
    tesseract-ocr-ita && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt
COPY . .
ENV PRODUCTION=1 DATA_DIR=/data
RUN mkdir -p /data
CMD gunicorn --chdir web server:app --bind 0.0.0.0:${PORT:-5000} --workers 2 --threads 4 --timeout 120
