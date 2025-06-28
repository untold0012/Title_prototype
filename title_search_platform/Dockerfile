FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libopenblas-dev \
    libomp-dev \
    tesseract-ocr \
    libtesseract-dev \
    poppler-utils \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    curl \
    tesseract-ocr-eng \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set NLTK data path for both install and runtime
ENV NLTK_DATA=/usr/share/nltk_data

# Copy only requirements first (for caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && pip install -r requirements.txt

# Download NLTK and spaCy models
RUN python -c "import nltk; nltk.download('punkt', download_dir='/usr/share/nltk_data')"
RUN python -m spacy download en_core_web_sm

# Copy app source and environment config
COPY ./app /app/app
COPY .env /app/.env

# Expose port and run the API
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
