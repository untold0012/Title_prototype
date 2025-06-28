from fastapi import FastAPI
from app import file_service, db_manager

# Ensure singleton instance is created before use
_ = db_manager.DBMetadataManager()

app = FastAPI(title="Title Search Platform API")

# Include routers
app.include_router(file_service.router, prefix="/files", tags=["File Operations"])

@app.on_event("startup")
def on_startup():
    """
    Actions to perform on application startup.
    - Create database tables.
    """
    print("Application starting up...")
    db_manager.db_metadata_manager.create_tables()
    print("Database tables checked/created.")

@app.get("/")
async def read_root():
    return {"message": "Welcome to the Title Search Platform API"}

if __name__ == "__main__":
    import uvicorn
    # This is for local development testing only.
    # In production, you'd use a proper ASGI server like Uvicorn or Hypercorn managed by Gunicorn.
    uvicorn.run(app, host="0.0.0.0", port=8000)
