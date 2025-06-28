import os
import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, DateTime, BigInteger
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError

# Load environment variables from .env file
load_dotenv()

# Database connection details from environment variables
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "password")
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "title_search_db") # This will be file_metadata_db from .env
MYSQL_PORT = os.getenv("MYSQL_PORT", "3306")

# Define the database URL for mysql-connector-python
DATABASE_URL = f"mysql+mysqlconnector://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"

# Create SQLAlchemy engine
try:
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
except Exception as e:
    print(f"Error creating database engine: {e}")
    engine = None
    SessionLocal = None

# Define Base for declarative models
Base = declarative_base()

# Define FileUpload model
class FileUpload(Base):
    __tablename__ = "file_uploads"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(255), nullable=False) # Specify length for String
    uploaded_time = Column(DateTime, default=datetime.datetime.utcnow)
    file_size = Column(BigInteger)
    total_pages = Column(Integer)

    def __repr__(self):
        return f"<FileUpload(id={self.id}, filename='{self.filename}', pages={self.total_pages})>"

def create_tables():
    """
    Creates the database tables if they don't exist.
    """
    if not engine:
        print("Database engine not initialized. Cannot create tables.")
        return
    try:
        Base.metadata.create_all(bind=engine)
        print("Tables created successfully (if they didn't exist).")
    except SQLAlchemyError as e:
        print(f"Error creating tables: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during table creation: {e}")


def log_file_metadata(filename: str, uploaded_time: datetime.datetime, file_size: int, total_pages: int) -> int | None:
    """
    Logs file metadata to the database.

    Args:
        filename (str): Name of the file.
        uploaded_time (datetime): Time of upload.
        file_size (int): Size of the file in bytes.
        total_pages (int): Total number of pages in the document.

    Returns:
        int | None: The ID of the newly inserted record, or None on failure.
    """
    if not SessionLocal:
        print("Database session not initialized. Cannot log metadata.")
        return None

    session = SessionLocal()
    try:
        new_file_log = FileUpload(
            filename=filename,
            uploaded_time=uploaded_time,
            file_size=file_size,
            total_pages=total_pages
        )
        session.add(new_file_log)
        session.commit()
        session.refresh(new_file_log)
        print(f"Successfully logged metadata for file: {filename}, ID: {new_file_log.id}")
        return new_file_log.id
    except SQLAlchemyError as e:
        print(f"Database error while logging metadata: {e}")
        session.rollback()
        return None
    except Exception as e:
        print(f"An unexpected error occurred while logging metadata: {e}")
        session.rollback()
        return None
    finally:
        session.close()

if __name__ == '__main__':
    # Example Usage (for testing purposes)
    # Make sure MySQL server is running, database exists, and .env is configured.
    # Note: .env should have MYSQL_DATABASE=file_metadata_db for this to match recent changes.
    print(f"Connecting to database: {MYSQL_DATABASE} on {MYSQL_HOST}")
    print("Attempting to create tables...")
    create_tables()

    print("\nAttempting to log file metadata...")
    now = datetime.datetime.utcnow()

    log_id = log_file_metadata(
        filename="example_document_readme_test.pdf",
        uploaded_time=now,
        file_size=1024 * 500,  # 500 KB
        total_pages=10
    )

    if log_id:
        print(f"Metadata logged successfully. Record ID: {log_id}")
    else:
        print("Failed to log metadata.")

    # Check .env for MYSQL_DATABASE value, it should be 'file_metadata_db'
    # The db_manager.py uses os.getenv("MYSQL_DATABASE", "title_search_db")
    # This default "title_search_db" will be overridden if .env has MYSQL_DATABASE=file_metadata_db
    # which it should from the previous subtask.
    # The print statement in __main__ will show what database name is being used.
