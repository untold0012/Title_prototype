# Start from a Python base image
FROM python:3.9-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set a working directory
WORKDIR /app

# Copy requirements.txt to the working directory
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the application code into the working directory
# This assumes your application code is in a directory named 'app' at the root
# of your build context, and your .env file is also at the root.
COPY ./app /app/app
COPY .env /app/.env

# Expose the port the application runs on
EXPOSE 8000

# Define the command to run the application
# Ensure your main FastAPI app instance is accessible via 'app.main:app'
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
