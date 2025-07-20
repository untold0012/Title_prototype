import os
from typing import IO, Optional
from urllib.parse import urlparse, urlunparse
from minio import Minio
from minio.error import S3Error
from dotenv import load_dotenv
import logging
from datetime import timedelta

# Load environment variables from .env file
load_dotenv()

# Logging setup
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Env vars
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000").replace("http://", "").replace("https://", "")
MINIO_PUBLIC_HOST = os.getenv("MINIO_PUBLIC_HOST", "minio")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "title-search-bucket")

logger.debug(f"MinIO config: endpoint={MINIO_ENDPOINT}, bucket={MINIO_BUCKET}")

class MinioMetadataManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MinioMetadataManager, cls).__new__(cls)
            try:
                cls.minio_client = Minio(
                    endpoint=MINIO_ENDPOINT,
                    access_key=MINIO_ACCESS_KEY,
                    secret_key=MINIO_SECRET_KEY,
                    secure=False,
                    region=""
                )
            except Exception as e:
                logger.error(f"Error initializing Minio client: {e}")
                cls.minio_client = None
        return cls._instance

    def upload_file(self, file_data: IO[bytes], object_name: str, file_length: int) -> Optional[str]:
        if not self.minio_client:
            logger.warning("Minio client not initialized.")
            return None

        try:
            if not self.minio_client.bucket_exists(MINIO_BUCKET):
                self.minio_client.make_bucket(MINIO_BUCKET)

            result = self.minio_client.put_object(
                MINIO_BUCKET,
                object_name,
                file_data,
                file_length
            )
            logger.info(f"[UPLOAD] {object_name} uploaded to {MINIO_BUCKET}, ETag: {result.etag}")
            return result.etag
        except S3Error as e:
            logger.error(f"[S3Error] {e}")
            return None
        except Exception as e:
            logger.error(f"[UPLOAD FAILED] {e}")
            return None

    def upload_bytes_to_minio(self, file_bytes: bytes, object_name: str, content_type: str = "application/octet-stream") -> Optional[str]:
        from io import BytesIO
        if not self.minio_client:
            logger.warning("Minio client not initialized.")
            return None

        try:
            if not self.minio_client.bucket_exists(MINIO_BUCKET):
                self.minio_client.make_bucket(MINIO_BUCKET)

            stream = BytesIO(file_bytes)
            result = self.minio_client.put_object(
                MINIO_BUCKET,
                object_name,
                stream,
                len(file_bytes),
                content_type=content_type
            )
            logger.info(f"[UPLOAD BYTES] {object_name} uploaded, ETag: {result.etag}")
            return result.etag
        except Exception as e:
            logger.error(f"[UPLOAD BYTES FAILED] {e}")
            return None

    def get_file_info(self, object_name: str) -> Optional[dict]:
        if not self.minio_client:
            logger.warning("Minio client not initialized.")
            return None
        try:
            stat = self.minio_client.stat_object(MINIO_BUCKET, object_name)
            return {
                "bucket": stat.bucket_name,
                "object_name": stat.object_name,
                "size": stat.size,
                "last_modified": stat.last_modified,
                "etag": stat.etag,
                "content_type": stat.content_type,
            }
        except S3Error as e:
            logger.error(f"[STAT ERROR] {e}")
            return None
        except Exception as e:
            logger.error(f"[UNEXPECTED STAT ERROR] {e}")
            return None

    @staticmethod
    def fix_presigned_url_hostname(url: str, new_hostname: str) -> str:
        parsed = urlparse(url)
        updated = parsed._replace(netloc=f"{new_hostname}:{9001}")
        return urlunparse(updated)

    def get_presigned_url(self, object_name: str, expiry_seconds: int = 3600) -> Optional[str]:
        if not self.minio_client:
            logger.warning("Minio client not initialized.")
            return None
        try:
            expires = timedelta(seconds=expiry_seconds)

            # Instead of fixing the URL after signing, sign it with the correct host directly
            public_client = Minio(
                endpoint=f"host.docker.internal:9000",  # 👈 sign using public host
                access_key=MINIO_ACCESS_KEY,
                secret_key=MINIO_SECRET_KEY,
                secure=False,
                region=""
            )

            signed_url = public_client.presigned_get_object(
                bucket_name=MINIO_BUCKET,
                object_name=object_name,
                expires=expires
            )
            logger.debug(f"[SIGNED URL] {signed_url}")
            return signed_url
        except Exception as e:
            logger.exception(f"[PRESIGNED URL ERROR] {e}")
            return None

# Singleton instance
minio_metadata_manager = MinioMetadataManager()

if __name__ == '__main__':
    from io import BytesIO
    dummy_data = BytesIO(b"test content")
    test_key = "labelstudio/images/test_upload.txt"
    minio_metadata_manager.upload_file(dummy_data, test_key, dummy_data.getbuffer().nbytes)
    print("Presigned URL:", minio_metadata_manager.get_presigned_url(test_key))
