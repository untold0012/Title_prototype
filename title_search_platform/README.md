# Title Search Platform

## Project Description

The Title Search Platform is a FastAPI-based application designed to allow users to upload PDF documents. The system extracts metadata from these documents (such as filename, size, and number of pages), stores the files in a MinIO object storage, and logs the metadata into a MySQL database. This platform serves as a foundational system for managing and searching through document titles (though the search functionality itself is not yet implemented).

The application is fully containerized using Docker and orchestrated with Docker Compose, providing a consistent development and deployment environment.

## Prerequisites

Before you begin, ensure you have the following installed on your system:
- Docker: [Install Docker](https://docs.docker.com/get-docker/)
- Docker Compose: [Install Docker Compose](https://docs.docker.com/compose/install/) (Often included with Docker Desktop)

## Getting Started

Follow these steps to get the application running:

1.  **Clone the Repository:**
    ```bash
    git clone <repository_url> # Replace <repository_url> with the actual URL
    cd title_search_platform
    ```

2.  **Configure Environment Variables:**
    The project uses an `.env` file to manage configuration settings, including database credentials and MinIO details. A default `.env` file is provided with example values suitable for local development using Docker Compose.

    Verify the `title_search_platform/.env` file. It should contain placeholders like:
    ```env
    # MinIO Configuration
    MINIO_ENDPOINT=http://minio:9000
    MINIO_ACCESS_KEY=minioadmin
    MINIO_SECRET_KEY=minioadmin
    MINIO_BUCKET=file-uploads

    # MySQL Database Configuration
    MYSQL_HOST=db
    MYSQL_DATABASE=file_metadata_db
    MYSQL_USER=user_db
    MYSQL_PASSWORD=password_db
    MYSQL_ROOT_PASSWORD=root_password_db
    MYSQL_PORT=3306
    ```
    If you need to change any of these (e.g., for a production setup or if default ports conflict), update them accordingly. **For production, all default credentials must be changed.**

3.  **Build and Run with Docker Compose:**
    Navigate to the root directory of the project (`title_search_platform`) where the `docker-compose.yml` file is located, and run:
    ```bash
    docker-compose up -d --build
    ```
    - `--build`: Forces Docker Compose to build the images (e.g., for the `api` service) before starting the containers.
    - `-d`: Runs the containers in detached mode (in the background).

    The first time you run this, Docker Compose will download the necessary images (MySQL, MinIO) and build the image for the API service. This might take a few minutes.

## Accessing the Services

Once the application is running, you can access its different components:

*   **API Documentation (Swagger UI):**
    The FastAPI application provides interactive API documentation via Swagger UI.
    -   URL: [http://localhost:8000/docs](http://localhost:8000/docs)
    -   You can use this interface to test the `/files/upload/` endpoint.

*   **MinIO Console:**
    MinIO provides a web-based console for managing buckets and objects.
    -   URL: [http://localhost:9001](http://localhost:9001)
    -   **Default Credentials** (from the example `.env` file):
        -   Access Key (Username): `minioadmin`
        -   Secret Key (Password): `minioadmin`
    You should find a bucket named `file-uploads` (as per `MINIO_BUCKET` in `.env`) once MinIO is initialized.

*   **MySQL Database:**
    The MySQL database is accessible on port `3306` of your host machine. You can connect to it using any MySQL client (e.g., DBeaver, MySQL Workbench, or `mysql` CLI).
    -   Host: `localhost`
    -   Port: `3306`
    -   User: `user_db` (as per `MYSQL_USER` in `.env`)
    -   Password: `password_db` (as per `MYSQL_PASSWORD` in `.env`)
    -   Database Name: `file_metadata_db` (as per `MYSQL_DATABASE` in `.env`)
    -   Root Password: `root_password_db` (as per `MYSQL_ROOT_PASSWORD` in `.env`)

## Stopping the Application

To stop all running services defined in the `docker-compose.yml` file, navigate to the project root and run:
```bash
docker-compose down
```
If you also want to remove the data volumes (MinIO data and MySQL data), you can use:
```bash
docker-compose down -v
```

## Project Structure

```
title_search_platform/
├── app/                  # Main application code
│   ├── main.py           # FastAPI app definition, startup events
│   ├── file_service.py   # FastAPI router for file uploads
│   ├── minio_manager.py  # MinIO client and operations
│   └── db_manager.py     # Database models and operations (SQLAlchemy)
├── Dockerfile            # Dockerfile for the API service
├── docker-compose.yml    # Docker Compose configuration
├── .env                  # Environment variables (gitignored in real projects)
├── requirements.txt      # Python dependencies
└── README.md             # This file
```

---
*This README provides basic setup and operational instructions. Further development would involve adding more features, robust error handling, security enhancements, and comprehensive testing.*
