import os
import datetime
import logging
from label_studio_sdk.client import LabelStudio
from label_studio_sdk.label_interface import LabelInterface
from fastapi import UploadFile, File, HTTPException
from typing import Annotated
import os
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
LABEL_STUDIO_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6ODA1ODM2NTk0OSwiaWF0IjoxNzUxMTY1OTQ5LCJqdGkiOiIzMmZlZGUwNDdiZjU0NTVmOWIxNTFjZjJmNTlmMjcxNSIsInVzZXJfaWQiOjJ9.EfpYrE1ZrH97eRj5aAFZPCVCMocp6FGYyeyMKZKhAls" 
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
        clean_text=clean_extracted_text(extracted_text)

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
        extracted_text=clean_text,
    )


@router.post("/create-label-task/")
async def create_label_task(file: Annotated[UploadFile, File()]):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    # Step 1: Extract text
    total_pages, extracted_text = extract_text_hybrid(file)

    # Step 2: Clean text
    cleaned_text = clean_extracted_text(extracted_text)

    # Step 3: Connect to Label Studio
    try:
        ls = LabelStudio(
            base_url=os.getenv("LABEL_STUDIO_URL", "http://labelstudio:8080"),
            api_key=LABEL_STUDIO_API_KEY
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Label Studio connection failed: {str(e)}")

    # Step 4: Create or reuse project
    project = None
    project_title = "NER Labeling (Auto)"
    try:
        for p in ls.projects.list():
            if p.title == project_title:
                project = p
                break

        if not project:
            label_config = """<View>
            <Labels name="label" toName="text">
                <Label value="GRANTOR" background="green"/>
                <Label value="GRANTEE" background="blue"/>
                <Label value="RECORDING_DATE" background="red"/>
                <Label value="INSTRUMENT_NUMBER" background="orange"/>
                <Label value="BOOK_PAGE" background="purple"/>
                <Label value="DATED_DATE" background="brown"/>
            </Labels>
            <Text name="text" value="$text"/>
            </View>"""

            try:
                project_resp = ls.projects.create(
                    title=project_title,
                    label_config=label_config
                )
                project = ls.projects.get(project_resp.id)
                logger.debug(project)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Project creation failed: {str(e)}")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Project creation failed: {str(e)}")

    # Step 5: Add task
    try:
        result = ls.projects.import_tasks(
            id=project.id,
            request=[{"data": {"text": cleaned_text}}]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Task import failed: {str(e)}")


    return {
        "message": "PDF extracted and task sent to Label Studio",
        "pages": total_pages,
        "filename": file.filename,
        "label_studio_project_id": project.id,
        "task_result": result
    }
