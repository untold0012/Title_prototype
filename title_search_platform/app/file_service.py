import json
import os
import datetime
import logging
from pathlib import Path
import subprocess
from label_studio_sdk.client import LabelStudio
from label_studio_sdk.label_interface import LabelInterface
from fastapi import UploadFile, File, HTTPException
from typing import Annotated
import os
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io
from typing import Annotated
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
import cv2
import numpy as np

from app.minio_manager import minio_metadata_manager
from app import db_manager
# from app.document_classifier import classify_doc_type

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

_ = db_manager.DBMetadataManager()

router = APIRouter()

LABEL_STUDIO_URL   = os.getenv("LABEL_STUDIO_URL", "http://labelstudio:8080")
LABEL_STUDIO_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6ODA1OTk4NDkzOSwiaWF0IjoxNzUyNzg0OTM5LCJqdGkiOiIyYmI4YmM5NWEyMjM0NDE3YmEzMmFhNzhjMzdmYTkzOCIsInVzZXJfaWQiOjJ9.44tEtjTw9q20qiw6fTWylprlwoAJzSBk4JQvldgrjZE" 
LABEL_STUDIO_PID   = os.getenv("LABEL_STUDIO_PID", "1")
PROJECT_TITLE = "NER Labeling (Auto)"

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
        if len(text) > 50:
            return False
        blocks = page.get_text("dict")["blocks"]
        has_text_blocks = any(block.get("type") == 0 and block.get("text", "").strip() for block in blocks)
        has_images = len(page.get_images(full=True)) > 0
        return not has_text_blocks and has_images

    def preprocess_image(pixmap: fitz.Pixmap) -> Image.Image:
        pil_img = Image.open(io.BytesIO(pixmap.tobytes("png"))).convert("L")
        img = np.array(pil_img)

        # Deskew
        coords = np.column_stack(np.where(img < 255))
        if coords.shape[0] > 0:
            angle = cv2.minAreaRect(coords)[-1]
            if angle < -45:
                angle = -(90 + angle)
            else:
                angle = -angle
            (h, w) = img.shape[:2]
            M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
            img = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

        # Binarize
        bin_img = cv2.adaptiveThreshold(img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                        cv2.THRESH_BINARY, 11, 2)

        # Resize small images
        if bin_img.shape[0] < 1000:
            bin_img = cv2.resize(bin_img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

        return Image.fromarray(bin_img)

    def is_ocr_result_valid(text: str) -> bool:
        lines = text.splitlines()
        num_chars = len(text)
        num_words = len(text.split())
        ascii_ratio = sum(c.isascii() for c in text) / max(1, num_chars)
        return num_chars > 100 and num_words > 15 and ascii_ratio > 0.85

    for i, page in enumerate(doc):
        try:
            if is_scanned_page(page):
                pix = page.get_pixmap(dpi=400)
                img = preprocess_image(pix)
                ocr_text = pytesseract.image_to_string(img, lang="eng", config="--psm 6 --oem 3")

                # OCR quality check
                if not is_ocr_result_valid(ocr_text):
                    logger.warning(f"OCR result for page {i+1} appears low quality.")

                extracted_text += f"--- Page {i+1} (OCR) ---\n{ocr_text.strip()}\n\n"
            else:
                blocks = page.get_text("blocks")
                block_texts = [b[4].strip() for b in blocks if isinstance(b[4], str) and b[4].strip()]
                page_text = "\n".join(block_texts)
                extracted_text += f"--- Page {i+1} (Text) ---\n{page_text.strip()}\n\n"
        except Exception as err:
            extracted_text += f"--- Page {i+1} ---\n[Error: {err}]\n\n"
            logger.error(f"Error extracting page {i+1}: {err}")

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
        upload_etag = minio_metadata_manager.upload_file(
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

@router.post("/create-label-task-donut/")
async def create_label_task(file: Annotated[UploadFile, File()]):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    # Step 1: Convert PDF pages to images
    file_bytes = await file.read()
    doc = fitz.open(stream=file_bytes, filetype="pdf")

    page_urls = []
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=300)
        img_bytes = pix.tobytes("png")
        img_name = f"{Path(file.filename).stem}_page_{i+1}.png"
        minio_path = f"labelstudio/images/{img_name}"

        try:
            minio_metadata_manager.upload_bytes_to_minio(
                file_bytes=img_bytes,
                object_name=minio_path,
                content_type="image/png"
            )
            public_url = minio_metadata_manager.get_presigned_url(minio_path)
            if public_url:
                page_urls.append(public_url)
            else:
                logger.warning(f"Presigned URL is None for path: {minio_path}")
        except Exception as e:
            logger.error(f"Failed to upload or generate URL for {minio_path}: {e}")
    print(f"Generated {page_urls} presigned URLs for Label Studio.")

    if not page_urls:
        raise HTTPException(status_code=500, detail="Failed to generate any presigned URLs for Label Studio.")

    # Step 2: Connect to Label Studio
    try:
        ls = LabelStudio(
            base_url=os.getenv("LABEL_STUDIO_URL", "http://labelstudio:8080"),
            api_key=LABEL_STUDIO_API_KEY
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Label Studio connection failed: {str(e)}")

    # Step 3: Create or reuse project with multi-image layout
    project_title = "Donut NER (Multi-Page Document)"
    label_config = """
        <View>
        <Header value="Multi-page document. Label using JSON below."/>
        <Image name="image" valueList="$images" zoom="true" />
        <TextArea name="ground_truth" toName="image" editable="true" required="true"
                    rows="10" value="$ground_truth"/>
        </View>
    """

    try:
        project = next((p for p in ls.projects.list() if p.title == project_title), None)
        if not project:
            project = ls.projects.create(title=project_title, label_config=label_config)
        else:
            project = ls.projects.get(project.id)
            ls.projects.update(project.id, label_config=label_config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Project creation failed: {str(e)}")

    # Step 4: Create one task per document, using list of image URLs
    try:
        task_payload = [{
            "images": page_urls,
            "ground_truth": json.dumps({
                "grantor": "",
                "grantee": "",
                "dated_date": "",
                "recorded_date": "",
                "consideration_amount": "",
                "document_name": ""
            }, indent=2),
        }]


        result = ls.projects.import_tasks(
            id=project.id,
            request=task_payload
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Task import failed: {str(e)}")

    return {
        "message": "Document sent to Label Studio as one task with multiple pages",
        "pages": len(page_urls),
        "label_studio_project_id": project.id,
        "task_result": result
    }


EXPORT_PATH = "/app/training/labelstudio/dev_data.json"
SPACY_OUTPUT_PATH = "/app/training/labelstudio/dev.spacy"
CONFIG_PATH = "app/training/config.cfg"
OUTPUT_DIR = "app/training/labelstudio/output"

@router.post("/export-and-train/")
def export_convert_and_train():
    try:
        # Step 1: Connect to Label Studio
        ls = LabelStudio(base_url=LABEL_STUDIO_URL, api_key=LABEL_STUDIO_API_KEY)
        project = ls.projects.get(LABEL_STUDIO_PID)

        # Step 2: Export annotations to local disk
        data = ls.projects.exports.as_json(project.id)
        logger.info(f"Exported data from Label Studio project {data}")
        try:
            logger.info(f"Entering export directory: {os.path.dirname(EXPORT_PATH)}")
            os.makedirs(os.path.dirname(EXPORT_PATH), exist_ok=True)
            with open(EXPORT_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"❌ Failed to write export file: {e}")
            raise

        # # Step 3: Convert to spaCy format
        # subprocess.run([
        #     "python", "app/training/convert_to_spacy_format.py",
        #     "--input", EXPORT_PATH,
        #     "--output", SPACY_OUTPUT_PATH
        # ], check=True)

        # Step 4: Fill missing values in config
        subprocess.run([
            "python", "-m", "spacy", "init", "fill-config",
            CONFIG_PATH, CONFIG_PATH
        ], check=True)

        # Step 5: Debug data
        debug_result = subprocess.run([
            "python", "-m", "spacy", "debug", "data", CONFIG_PATH,
            "--paths.train", SPACY_OUTPUT_PATH,
            "--paths.dev", SPACY_OUTPUT_PATH
        ], capture_output=True, text=True)
        if debug_result.returncode != 0:
            print("❌ spaCy debug failed:")
            print(debug_result.stdout)
            print(debug_result.stderr)
            raise RuntimeError("spaCy debug error")

        # Step 6: Train spaCy model
        result = subprocess.run([
            "python", "-m", "spacy", "train", CONFIG_PATH,
            "--output", OUTPUT_DIR,
            "--paths.train", SPACY_OUTPUT_PATH,
            "--paths.dev", SPACY_OUTPUT_PATH
        ], capture_output=True, text=True)

        if result.returncode != 0:
            print("❌ spaCy training failed:")
            print(result.stdout)
            print(result.stderr)
            raise RuntimeError("spaCy training error")
        else:
            print("✅ spaCy training succeeded")
            print(result.stdout)

        return {
            "message": "Exported, converted, and trained successfully",
            "export_file": EXPORT_PATH,
            "spacy_format_file": SPACY_OUTPUT_PATH,
            "model_output_dir": OUTPUT_DIR
        }

    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Script failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

