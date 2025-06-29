FROM python:3.10-slim

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

# Set NLTK data path
ENV NLTK_DATA=/usr/share/nltk_data

# Copy only requirements first for Docker cache optimization
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && pip install -r requirements.txt

# Download required NLTK and spaCy models
RUN python -c "import nltk; \
    nltk.download('punkt', download_dir='$NLTK_DATA'); \
    nltk.download('averaged_perceptron_tagger', download_dir='$NLTK_DATA'); \
    nltk.download('wordnet', download_dir='$NLTK_DATA'); \
    nltk.download('omw-1.4', download_dir='$NLTK_DATA')"

RUN python -m spacy download en_core_web_sm

# Copy app source and .env
COPY ./app /app/app
COPY .env /app/.env

# Expose FastAPI port
EXPOSE 8000

# Start API server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
