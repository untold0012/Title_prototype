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
    libgl1 \
    curl \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy only requirements for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy app source and .env
COPY ./app /app/app
COPY .env /app/.env

# Expose FastAPI port
EXPOSE 8000

# Start the FastAPI app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
