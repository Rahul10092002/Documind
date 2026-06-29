from sqlalchemy.orm import Session
from app.models import Document
from app.exceptions import DocumentNotFoundError
from fastapi import UploadFile
import shutil
import os


class DocumentService:
    def get(self, db: Session, doc_id: int) -> Document:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            raise DocumentNotFoundError(f"Document {doc_id} not found")
        return doc

    def list_all(self, db: Session, skip: int = 0, limit: int = 20):
        return db.query(Document).offset(skip).limit(limit).all()

    async def create(self, db: Session, file: UploadFile) -> Document:
        save_path = f"uploads/{file.filename}"
        os.makedirs("uploads", exist_ok=True)
        with open(save_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        doc = Document(filename=file.filename, file_path=save_path, status="uploaded")
        db.add(doc)
        db.commit()
        db.refresh(doc)
        return doc

    def delete(self, db: Session, doc_id: int) -> None:
        doc = self.get(db, doc_id)
        db.delete(doc)
        db.commit()
