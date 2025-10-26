import os
import io
import json
import datetime
import subprocess
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import List, Dict
import fitz  # PyMuPDF
from PIL import Image
import cv2
import numpy as np

router = APIRouter()

# Directory paths for training
DONUT_DATA_DIR = Path("/app/training/donut_dataset")
MODEL_OUTPUT_DIR = Path("/app/training/donut_model")

# Models for request
class DocumentEntity(BaseModel):
    document_type: str
    start_page: int
    end_page: int
    entities: Dict[str, str]

class DonutUploadRequest(BaseModel):
    documents: List[DocumentEntity]

# --- Image preprocessing helpers ---
def preprocess_image(pixmap: fitz.Pixmap) -> Image.Image:
    """Convert PDF page to preprocessed PIL image suitable for Donut."""
    img = Image.open(io.BytesIO(pixmap.tobytes("png"))).convert("L")
    arr = np.array(img)

    # Deskew
    coords = np.column_stack(np.where(arr < 255))
    if coords.shape[0] > 0:
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
        (h, w) = arr.shape[:2]
        M = cv2.getRotationMatrix2D((w//2, h//2), angle, 1.0)
        arr = cv2.warpAffine(arr, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

    # Binarize
    arr = cv2.adaptiveThreshold(arr, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                cv2.THRESH_BINARY, 11, 2)

    # Resize if too small
    if arr.shape[0] < 1000:
        arr = cv2.resize(arr, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

    return Image.fromarray(arr)

# --- Main upload + train endpoint ---
@router.post("/upload-and-train-donut/")
async def upload_and_train_donut(file: UploadFile = File(...), metadata: DonutUploadRequest = None):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files supported.")

    # Step 1: Read PDF
    pdf_bytes = await file.read()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    # Step 2: Prepare Donut dataset directory
    DONUT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # Step 3: For each document in metadata, extract pages and save image + JSON
    sample_count = 0
    for document in metadata.documents:
        for page_num in range(document.start_page-1, document.end_page):
            page = doc[page_num]
            pix = page.get_pixmap(dpi=300)
            img = preprocess_image(pix)
            # Save image
            img_name = f"{Path(file.filename).stem}_doc{sample_count+1}_page{page_num+1}.png"
            img_path = DONUT_DATA_DIR / img_name
            img.save(img_path)

            # Save JSON in Donut format
            gt_str = json.dumps(document.entities)  # Must be string for Donut
            json_sample = {"image_path": str(img_path), "ground_truth": gt_str}
            json_path = DONUT_DATA_DIR / f"{img_name}.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(json_sample, f)
            sample_count += 1

    # Step 4: Trigger Donut training
    try:
        result = subprocess.run([
            "python", "train_donut.py",  # Your Donut training script
            "--data_dir", str(DONUT_DATA_DIR),
            "--output_dir", str(MODEL_OUTPUT_DIR)
        ], capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Donut training failed:\n{e.stdout}\n{e.stderr}")

    return {
        "message": f"Uploaded PDF, generated {sample_count} training samples, and trained Donut successfully.",
        "model_output_dir": str(MODEL_OUTPUT_DIR)
    }
