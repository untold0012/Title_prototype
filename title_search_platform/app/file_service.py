import os
import shutil
import datetime
from typing import IO, Annotated

import pdfplumber
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from title_search_platform.app import minio_manager
from title_search_platform.app import db_manager

# Create an APIRouter instance
router = APIRouter()

# Define Pydantic model for the response
class FileUploadResponse(BaseModel):
    db_id: int
    filename: str
    message: str
    minio_object_name: str
    file_size: int
    total_pages: int
    uploaded_time: datetime.datetime


@router.post("/upload/", response_model=FileUploadResponse)
async def upload_pdf_file(file: Annotated[UploadFile, File()]):
    """
    Uploads a PDF file, extracts metadata, stores it in MinIO, and logs metadata in the database.
    """
    # Validate file type (must be PDF)
    if not (file.filename.lower().endswith(".pdf") or file.content_type == "application/pdf"):
        raise HTTPException(status_code=400, detail="Invalid file type. Only PDF files are accepted.")

    filename = file.filename
    uploaded_time = datetime.datetime.utcnow()

    # For pdfplumber and MinIO, we need to work with the file content.
    # UploadFile.file is a SpooledTemporaryFile. We can read from it directly.

    # To get file_size reliably and allow multiple reads (for pdfplumber and MinIO upload)
    # we read it once.
    file.file.seek(0, os.SEEK_END)
    file_size = file.file.tell()  # Get the size of the file
    file.file.seek(0)  # Reset cursor to the beginning for subsequent reads

    if file_size == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # Count pages using pdfplumber
    total_pages = None
    try:
        # pdfplumber needs a file path or a file-like object that it can manage.
        # We pass the SpooledTemporaryFile directly.
        with pdfplumber.open(file.file) as pdf:
            total_pages = len(pdf.pages)
        file.file.seek(0) # Reset cursor again for MinIO upload
    except Exception as e:
        # Log the error or handle it more gracefully
        print(f"Error processing PDF for page count: {e}")
        # If pdfplumber fails, we might still want to upload the file,
        # or we might consider it a failure. For now, let's raise an error.
        raise HTTPException(status_code=500, detail=f"Error processing PDF to count pages: {str(e)}")


    # Store the file in MinIO
    # We can use the filename as the object name, or generate a unique one.
    # For simplicity, using the original filename. Consider collision implications.
    minio_object_name = filename
    try:
        # minio_manager.upload_file now expects a file-like object and its length
        upload_etag = minio_manager.upload_file(
            file_data=file.file,  # Pass the SpooledTemporaryFile
            object_name=minio_object_name,
            file_length=file_size
        )
        if not upload_etag:
            raise HTTPException(status_code=500, detail="Failed to upload file to MinIO.")
    except Exception as e:
        # Log the error
        print(f"MinIO upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"MinIO upload failed: {str(e)}")
    finally:
        # Ensure the temporary file is closed
        await file.close()


    # Log metadata in MySQL database
    db_id = None
    try:
        db_id = db_manager.log_file_metadata(
            filename=filename,
            uploaded_time=uploaded_time,
            file_size=file_size,
            total_pages=total_pages
        )
        if db_id is None:
            # If logging fails, consider how to handle the already uploaded MinIO file.
            # For now, we raise an error. A more robust solution might involve cleanup.
            raise HTTPException(status_code=500, detail="Failed to log file metadata to database.")
    except Exception as e:
        # Log the error
        print(f"Database logging failed: {e}")
        # Consider cleanup of MinIO object if DB log fails permanently
        raise HTTPException(status_code=500, detail=f"Database logging failed: {str(e)}")

    return FileUploadResponse(
        db_id=db_id,
        filename=filename,
        message="File uploaded, processed, and metadata logged successfully.",
        minio_object_name=minio_object_name,
        file_size=file_size,
        total_pages=total_pages,
        uploaded_time=uploaded_time
    )

# To test this service, you would typically run it with Uvicorn and send a POST request
# using a tool like curl or Postman.
# Example: uvicorn title_search_platform.app.main:app --reload
# (Assuming main.py will include this router)
