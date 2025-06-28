import os
from typing import IO, Optional  # Added Optional for Python 3.9 compatibility
from minio import Minio
from minio.error import S3Error
from dotenv import load_dotenv
import logging

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# MinIO connection details from environment variables
# MINIO_ENDPOINT should be only host:port (e.g., 'localhost:9000'), no path allowed
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "title-search-bucket")

logger.debug(f"MinIO config: endpoint={MINIO_ENDPOINT}, bucket={MINIO_BUCKET}, access_key length={len(MINIO_ACCESS_KEY)}, secret_key length={len(MINIO_SECRET_KEY)}")

class MinioMetadataManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MinioMetadataManager, cls).__new__(cls)
            try:
                cls.minio_client = Minio(
                    MINIO_ENDPOINT,
                    access_key=MINIO_ACCESS_KEY,
                    secret_key=MINIO_SECRET_KEY,
                    secure=False
                )
            except Exception as e:
                logger.error(f"Error initializing Minio client: {e}")
                cls.minio_client = None
        return cls._instance

    def upload_file(self, file_data: IO[bytes], object_name: str, file_length: int) -> Optional[str]:
        """
        Uploads a file (from a file-like object) to the specified MinIO bucket.
        Creates the bucket if it doesn't already exist.

        Args:
            file_data (IO[bytes]): File-like object containing the data to upload.
            object_name (str): Name of the object in MinIO.
            file_length (int): Length of the file in bytes.

        Returns:
            Optional[str]: ETag of the uploaded object on success, None otherwise.
        """
        if not self.minio_client:
            logger.warning("Minio client not initialized.")
            return None

        try:
            # Check if the bucket exists, create it if not
            found = self.minio_client.bucket_exists(MINIO_BUCKET)
            if not found:
                self.minio_client.make_bucket(MINIO_BUCKET)
                logger.info(f"Bucket '{MINIO_BUCKET}' created.")
            else:
                logger.info(f"Bucket '{MINIO_BUCKET}' already exists.")

            # Upload the file using put_object
            result = self.minio_client.put_object(
                MINIO_BUCKET, object_name, file_data, length=file_length
            )
            logger.info(
                f"File-like object uploaded as '{object_name}' to bucket '{MINIO_BUCKET}'. "
                f"ETag: {result.etag}"
            )
            return result.etag
        except S3Error as e:
            logger.error(f"MinIO S3 Error during file upload: {e}")
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred during file upload: {e}")
            return None

    def get_file_info(self, object_name: str) -> Optional[dict]:
        """
        Retrieves metadata of a file from MinIO.

        Args:
            object_name (str): Name of the object in MinIO.

        Returns:
            Optional[dict]: Object statistics on success, None otherwise.
        """
        if not self.minio_client:
            logger.warning("Minio client not initialized.")
            return None

        try:
            stat = self.minio_client.stat_object(MINIO_BUCKET, object_name)
            logger.info(f"Successfully retrieved info for object '{object_name}': {stat}")
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
                logger.error(f"Error: Object '{object_name}' not found in bucket '{MINIO_BUCKET}'.")
            else:
                logger.error(f"MinIO S3 Error during file info retrieval: {e}")
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred during file info retrieval: {e}")
            return None

# Usage example:
minio_metadata_manager = MinioMetadataManager()

if __name__ == '__main__':
    # Example Usage (for testing purposes)
    # Make sure MinIO server is running and .env is configured.
    # This test is now more conceptual as it requires a file-like object.

    from io import BytesIO

    logger.info("Attempting to upload a test byte stream...")
    dummy_file_content = b"This is a test byte stream for MinIO upload."
    dummy_file_length = len(dummy_file_content)
    dummy_file_data = BytesIO(dummy_file_content)

    uploaded_etag = minio_metadata_manager.upload_file(dummy_file_data, "test_object_bytes.txt", dummy_file_length)

    if uploaded_etag:
        logger.info(f"Upload successful! ETag: {uploaded_etag}")
        logger.info("\nAttempting to get file info for 'test_object_bytes.txt'...")
        file_info = minio_metadata_manager.get_file_info("test_object_bytes.txt")
        if file_info:
            logger.info("File info retrieved successfully:", file_info)
        else:
            logger.warning("Failed to retrieve file info.")
    else:
        logger.warning("Upload failed.")

    # To test with an actual file, you would do:
    # dummy_file_path = "test_upload.txt"
    # with open(dummy_file_path, "w") as f:
    #     f.write("This is a test file for MinIO upload.")
    #
    # with open(dummy_file_path, "rb") as f_obj:
    #     file_stat = os.stat(dummy_file_path)
    #     uploaded_etag = minio_metadata_manager.upload_file(f_obj, "test_object_from_file.txt", file_stat.st_size)
    #     if uploaded_etag:
    #         logger.info(f"File upload successful! ETag: {uploaded_etag}")
    #     else:
    #         logger.warning("File upload failed.")
    # if os.path.exists(dummy_file_path):
    #    os.remove(dummy_file_path)
