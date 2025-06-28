import os
import datetime
import logging

import requests
from app.entity_extractor import extract_entities_semantic
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io
from typing import Annotated
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from app import minio_manager
from app import db_manager
from app.document_classifier import classify_doc_type

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

_ = minio_manager.MinioMetadataManager()
_ = db_manager.DBMetadataManager()

router = APIRouter()

LABEL_STUDIO_URL   = os.getenv("LABEL_STUDIO_URL", "http://labelstudio:8080")
LABEL_STUDIO_TOKEN = os.getenv("LABEL_STUDIO_TOKEN", "changeme")
LABEL_STUDIO_PID   = os.getenv("LABEL_STUDIO_PID", "1")

class FileUploadResponse(BaseModel):
    db_id: int
    filename: str
    message: str
    minio_object_name: str
    file_size: int
    total_pages: int
    uploaded_time: datetime.datetime
    extracted_text: str
    document_type: str
    extracted_entities: dict

class TextInput(BaseModel):
    text: str

def extract_text_hybrid(file: UploadFile) -> tuple[int, str]:
    file.file.seek(0)
    file_bytes = file.file.read()
    doc = fitz.open(stream=file_bytes, filetype="pdf")

    extracted_text = ""
    total_pages = len(doc)

    def is_scanned_page(page: fitz.Page) -> bool:
        text = page.get_text("text").strip()
        if len(text) > 30:
            return False
        blocks = page.get_text("dict")["blocks"]
        has_text_blocks = any(block.get("type") == 0 for block in blocks)
        if has_text_blocks:
            return False
        has_images = len(page.get_images(full=True)) > 0
        return has_images or not text

    for i, page in enumerate(doc):
        try:
            if is_scanned_page(page):
                pix = page.get_pixmap(dpi=300)
                img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")
                ocr_text = pytesseract.image_to_string(img, lang="eng")
                extracted_text += f"--- Page {i+1} (OCR) ---\n{ocr_text.strip()}\n\n"
            else:
                text = page.get_text().strip()
                extracted_text += f"--- Page {i+1} (Text) ---\n{text}\n\n"
        except Exception as err:
            extracted_text += f"--- Page {i+1} ---\n[Error: {err}]\n\n"

    return total_pages, extracted_text.strip()


def clean_extracted_text(text: str) -> str:
    import re
    text = re.sub(r'--- Page \d+ \(OCR\) ---', '', text)
    text = re.sub(r'\n{2,}', '\n\n', text)  # condense blank lines
    return text.strip()

def save_clean_text_for_label_studio(text: str, doc_id: str) -> str:
    labelstudio_dir = Path(__file__).parent / "training" / "labelstudio"
    labelstudio_dir.mkdir(parents=True, exist_ok=True)
    path = labelstudio_dir / f"{doc_id}.txt"
    with open(path, "w") as f:
        f.write(text)
    return str(path)

@router.post("/upload/", response_model=FileUploadResponse)
async def upload_pdf_file(file: Annotated[UploadFile, File()]):
    if not (file.filename.lower().endswith(".pdf") or file.content_type == "application/pdf"):
        raise HTTPException(status_code=400, detail="Invalid file type. Only PDF files are accepted.")

    filename = file.filename
    uploaded_time = datetime.datetime.utcnow()

    file.file.seek(0, os.SEEK_END)
    file_size = file.file.tell()
    file.file.seek(0)

    if file_size == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        total_pages, extracted_text = extract_text_hybrid(file)
        file.file.seek(0)

        document_type = classify_doc_type(extracted_text)
        extracted_entities = extract_entities_semantic(extracted_text, document_type)

    except Exception as e:
        logger.error(f"Text extraction or entity extraction failed: {e}")
        raise HTTPException(status_code=500, detail="Text or entity extraction failed.")

    minio_object_name = filename
    logger.debug(f"Preparing to upload file: {filename}, size: {file_size}, pages: {total_pages}")
    try:
        upload_etag = minio_manager.minio_metadata_manager.upload_file(
            file_data=file.file,
            object_name=minio_object_name,
            file_length=file_size
        )
        if not upload_etag:
            raise HTTPException(status_code=500, detail="Failed to upload file to MinIO.")
    except Exception as e:
        logger.error(f"MinIO upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"MinIO upload failed: {str(e)}")
    finally:
        await file.close()

    try:
        db_id = db_manager.db_metadata_manager.log_file_metadata(
            filename=filename,
            uploaded_time=uploaded_time,
            file_size=file_size,
            total_pages=total_pages
        )
        if db_id is None:
            raise HTTPException(status_code=500, detail="Failed to log file metadata to database.")
    except Exception as e:
        logger.error(f"Database logging failed: {e}")
        raise HTTPException(status_code=500, detail=f"Database logging failed: {str(e)}")

    return FileUploadResponse(
        db_id=db_id,
        filename=filename,
        message="File uploaded, processed, and metadata logged successfully.",
        minio_object_name=minio_object_name,
        file_size=file_size,
        total_pages=total_pages,
        uploaded_time=uploaded_time,
        extracted_text=extracted_text,
        document_type=document_type,
        extracted_entities=extracted_entities
    )

@router.post("/create-label-task/")
async def create_label_task(file: Annotated[UploadFile, File()]):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    # Step 1: Extract text using your hybrid extractor
    total_pages, extracted_text = extract_text_hybrid(file)

    # Step 2: Clean the text
    cleaned_text = clean_extracted_text(extracted_text)

    # Step 3: Prepare and send to Label Studio
    task = {"data": {"text": cleaned_text}}
    headers = {
        "Authorization": f"Token {LABEL_STUDIO_TOKEN}",
        "Content-Type": "application/json"
    }
    url = f"{LABEL_STUDIO_URL}/api/projects/{LABEL_STUDIO_PID}/import?format=JSON"

    try:
        resp = requests.post(url, json=[task], headers=headers, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Label Studio API error: {str(e)}")

    return {
        "message": "PDF extracted and task sent to Label Studio",
        "pages": total_pages,
        "filename": file.filename,
        "response": resp.json()
    }
