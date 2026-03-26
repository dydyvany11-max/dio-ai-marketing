from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from src.api.schemas import (
    VKKnowledgeBaseItemResponse,
    VKKnowledgeBaseListResponse,
    VKKnowledgeFileItemResponse,
    VKKnowledgeBaseUploadRequest,
    VKKnowledgeBaseUploadResponse,
    VKKnowledgeDeleteFileResponse,
)
from src.api.services.vk_knowledge import VKKnowledgeStore

router = APIRouter(prefix="/vk", tags=["VK"])

_knowledge_store = VKKnowledgeStore()
_SUPPORTED_KB_FILE_EXTENSIONS = {
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".yml",
    ".yaml",
    ".ini",
    ".log",
    ".xml",
    ".html",
    ".htm",
    ".pdf",
}


def _decode_uploaded_text(raw_bytes: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp1251"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("latin-1", errors="replace")


def _extract_pdf_text(raw_bytes: bytes) -> str:
    try:
        from pypdf import PdfReader
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="PDF parsing is unavailable: install 'pypdf'",
        ) from exc

    try:
        reader = PdfReader(BytesIO(raw_bytes))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to read PDF: {exc}") from exc

    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail="PDF is encrypted and cannot be parsed without password",
            ) from exc

    pages_text: list[str] = []
    for page in reader.pages:
        try:
            text = (page.extract_text() or "").strip()
        except Exception:
            text = ""
        if text:
            pages_text.append(text)

    return "\n\n".join(pages_text).strip()


def _decode_uploaded_content(filename: str, raw_bytes: bytes) -> str:
    extension = Path(filename).suffix.lower()
    if extension == ".pdf":
        return _extract_pdf_text(raw_bytes)
    return _decode_uploaded_text(raw_bytes)


def _build_kb_item(
    entry: dict,
    *,
    content_length: int | None = None,
) -> VKKnowledgeBaseItemResponse:
    files: list[VKKnowledgeFileItemResponse] = []
    for doc in (entry.get("documents") or []):
        if str(doc.get("source_type") or "").strip().lower() != "file":
            continue
        files.append(
            VKKnowledgeFileItemResponse(
                id=str(doc.get("id") or ""),
                filename=str(doc.get("filename") or ""),
                title=(str(doc.get("title") or "").strip() or None),
                source_type=str(doc.get("source_type") or ""),
                mime_type=(str(doc.get("mime_type") or "").strip() or None),
                content_length=len(str(doc.get("content") or "")),
                created_at=doc.get("created_at"),
                updated_at=doc.get("updated_at"),
            )
        )

    final_content_length = (
        int(content_length)
        if content_length is not None
        else len(str(entry.get("content") or ""))
    )
    return VKKnowledgeBaseItemResponse(
        id=str(entry.get("id") or ""),
        name=str(entry.get("name") or ""),
        language=str(entry.get("language") or "ru"),
        content_length=final_content_length,
        created_at=entry.get("created_at"),
        updated_at=entry.get("updated_at"),
        is_active=bool(entry.get("is_active")),
        files=files,
    )


@router.get(
    "/knowledge",
    response_model=VKKnowledgeBaseListResponse,
    summary="List uploaded VK knowledge bases",
)
def vk_list_knowledge_bases():
    rows = _knowledge_store.list_items()
    items: list[VKKnowledgeBaseItemResponse] = []
    for row in rows:
        kb_id = str(row.get("id") or "")
        loaded = _knowledge_store.get(kb_id)
        source = loaded or row
        items.append(
            _build_kb_item(
                source,
                content_length=int(row.get("content_length") or 0),
            )
        )
    return VKKnowledgeBaseListResponse(
        items=items,
    )


@router.post(
    "/knowledge/upload",
    response_model=VKKnowledgeBaseUploadResponse,
    summary="Upload or update VK knowledge base",
)
def vk_upload_knowledge_base(payload: VKKnowledgeBaseUploadRequest):
    active = _knowledge_store.get_active()
    target_kb_id = str(active.get("id") or "") if active else None
    try:
        entry = _knowledge_store.upsert(
            name=payload.name,
            content=payload.content,
            language=payload.language,
            knowledge_base_id=target_kb_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    item = _build_kb_item(entry)
    return VKKnowledgeBaseUploadResponse(item=item)


@router.post(
    "/knowledge/upload-file",
    response_model=VKKnowledgeBaseUploadResponse,
    summary="Upload file into SQLite knowledge base",
)
def vk_upload_knowledge_file(
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    language: str = Form(default="ru"),
):
    filename = (file.filename or "").strip()
    extension = Path(filename).suffix.lower()
    if extension not in _SUPPORTED_KB_FILE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported file type. Allowed: "
                + ", ".join(sorted(_SUPPORTED_KB_FILE_EXTENSIONS))
            ),
        )

    raw = file.file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    text_content = _decode_uploaded_content(filename, raw).strip()
    if not text_content:
        if extension == ".pdf":
            raise HTTPException(
                status_code=400,
                detail="PDF has no readable text (possibly scanned image PDF)",
            )
        raise HTTPException(status_code=400, detail="Uploaded file has no readable text")

    active = _knowledge_store.get_active()
    target_kb_id = str(active.get("id") or "") if active else None
    try:
        entry = _knowledge_store.add_file(
            filename=filename,
            content=text_content,
            mime_type=file.content_type,
            language=language,
            name=name,
            knowledge_base_id=target_kb_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    item = _build_kb_item(entry)
    return VKKnowledgeBaseUploadResponse(item=item)


@router.delete(
    "/knowledge/files/{document_id}",
    response_model=VKKnowledgeDeleteFileResponse,
    summary="Delete one file/document from knowledge base",
)
def vk_delete_knowledge_file(
    document_id: str,
    knowledge_base_id: str | None = Query(default=None),
):
    try:
        result = _knowledge_store.delete_document(
            document_id=document_id,
            knowledge_base_id=knowledge_base_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return VKKnowledgeDeleteFileResponse(
        deleted=True,
        document_id=str(result.get("document_id") or ""),
        knowledge_base_id=str(result.get("knowledge_base_id") or ""),
        remaining_documents=int(result.get("remaining_documents") or 0),
    )


@router.delete(
    "/knowledge/files",
    response_model=VKKnowledgeDeleteFileResponse,
    summary="Delete one file/document from knowledge base by filename",
)
def vk_delete_knowledge_file_by_name(
    filename: str = Query(...),
    knowledge_base_id: str | None = Query(default=None),
):
    try:
        result = _knowledge_store.delete_document_by_filename(
            filename=filename,
            knowledge_base_id=knowledge_base_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return VKKnowledgeDeleteFileResponse(
        deleted=True,
        document_id=str(result.get("document_id") or ""),
        knowledge_base_id=str(result.get("knowledge_base_id") or ""),
        remaining_documents=int(result.get("remaining_documents") or 0),
    )
