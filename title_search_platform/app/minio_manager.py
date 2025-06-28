import os
from typing import IO
from minio import Minio
from minio.error import S3Error
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# MinIO connection details from environment variables
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "title-search-bucket")

# Initialize Minio client
try:
    minio_client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False  # Set to True if using HTTPS
    )
except Exception as e:
    print(f"Error initializing Minio client: {e}")
    minio_client = None

def upload_file(file_data: IO[bytes], object_name: str, file_length: int) -> str | None:
    """
    Uploads a file (from a file-like object) to the specified MinIO bucket.
    Creates the bucket if it doesn't already exist.

    Args:
        file_data (IO[bytes]): File-like object containing the data to upload.
        object_name (str): Name of the object in MinIO.
        file_length (int): Length of the file in bytes.

    Returns:
        str | None: ETag of the uploaded object on success, None otherwise.
    """
    if not minio_client:
        print("Minio client not initialized.")
        return None

    try:
        # Check if the bucket exists, create it if not
        found = minio_client.bucket_exists(MINIO_BUCKET)
        if not found:
            minio_client.make_bucket(MINIO_BUCKET)
            print(f"Bucket '{MINIO_BUCKET}' created.")
        else:
            print(f"Bucket '{MINIO_BUCKET}' already exists.")

        # Upload the file using put_object
        result = minio_client.put_object(
            MINIO_BUCKET, object_name, file_data, length=file_length
        )
        print(
            f"File-like object uploaded as '{object_name}' to bucket '{MINIO_BUCKET}'. "
            f"ETag: {result.etag}"
        )
        return result.etag
    except S3Error as e:
        print(f"MinIO S3 Error during file upload: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during file upload: {e}")
        return None

def get_file_info(object_name: str) -> dict | None:
    """
    Retrieves metadata of a file from MinIO.

    Args:
        object_name (str): Name of the object in MinIO.

    Returns:
        dict | None: Object statistics on success, None otherwise.
    """
    if not minio_client:
        print("Minio client not initialized.")
        return None

    try:
        stat = minio_client.stat_object(MINIO_BUCKET, object_name)
        print(f"Successfully retrieved info for object '{object_name}': {stat}")
        return {
            "bucket": stat.bucket_name,
            "object_name": stat.object_name,
            "size": stat.size,
            "last_modified": stat.last_modified,
            "etag": stat.etag,
            "content_type": stat.content_type,
        }
    except S3Error as e:
        if e.code == "NoSuchKey":
            print(f"Error: Object '{object_name}' not found in bucket '{MINIO_BUCKET}'.")
        else:
            print(f"MinIO S3 Error during file info retrieval: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during file info retrieval: {e}")
        return None

if __name__ == '__main__':
    # Example Usage (for testing purposes)
    # Make sure MinIO server is running and .env is configured.
    # This test is now more conceptual as it requires a file-like object.

    from io import BytesIO

    print("Attempting to upload a test byte stream...")
    dummy_file_content = b"This is a test byte stream for MinIO upload."
    dummy_file_length = len(dummy_file_content)
    dummy_file_data = BytesIO(dummy_file_content)

    uploaded_etag = upload_file(dummy_file_data, "test_object_bytes.txt", dummy_file_length)

    if uploaded_etag:
        print(f"Upload successful! ETag: {uploaded_etag}")
        print("\nAttempting to get file info for 'test_object_bytes.txt'...")
        file_info = get_file_info("test_object_bytes.txt")
        if file_info:
            print("File info retrieved successfully:", file_info)
        else:
            print("Failed to retrieve file info.")
    else:
        print("Upload failed.")

    # To test with an actual file, you would do:
    # dummy_file_path = "test_upload.txt"
    # with open(dummy_file_path, "w") as f:
    #     f.write("This is a test file for MinIO upload.")
    #
    # with open(dummy_file_path, "rb") as f_obj:
    #     file_stat = os.stat(dummy_file_path)
    #     uploaded_etag = upload_file(f_obj, "test_object_from_file.txt", file_stat.st_size)
    #     if uploaded_etag:
    #         print(f"File upload successful! ETag: {uploaded_etag}")
    #     else:
    #         print("File upload failed.")
    # if os.path.exists(dummy_file_path):
    #    os.remove(dummy_file_path)
