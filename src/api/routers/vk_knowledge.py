from io import BytesIO
from pathlib import Path
import re
import uuid
from urllib.parse import urlparse

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
import requests
import trafilatura

from src.api.schemas import (
    VKKnowledgeBaseItemResponse,
    VKKnowledgeBaseListResponse,
    VKKnowledgeFileItemResponse,
    VKKnowledgeBaseUploadRequest,
    VKKnowledgeUrlUploadRequest,
    VKKnowledgeBaseUploadResponse,
    VKKnowledgeDeleteFileResponse,
)
from src.api.config import PROJECT_ROOT
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
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".gif",
}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
_KB_ASSETS_DIR = PROJECT_ROOT / "db" / "knowledge_assets"


def _save_image_asset(raw_bytes: bytes, extension: str) -> str:
    _KB_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    normalized_ext = (extension or "").strip().lower() or ".img"
    if not normalized_ext.startswith("."):
        normalized_ext = f".{normalized_ext}"
    filename = f"{uuid.uuid4().hex}{normalized_ext}"
    target = _KB_ASSETS_DIR / filename
    target.write_bytes(raw_bytes)
    return str(target.relative_to(PROJECT_ROOT)).replace("\\", "/")


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


def _extract_image_text(raw_bytes: bytes) -> str:
    try:
        from PIL import Image
        import pytesseract
    except Exception:
        return ""

    try:
        image = Image.open(BytesIO(raw_bytes))
    except Exception:
        return ""

    text_variants: list[str] = []
    for lang in ("rus+eng", "eng"):
        try:
            extracted = (pytesseract.image_to_string(image, lang=lang) or "").strip()
        except Exception:
            extracted = ""
        if extracted:
            text_variants.append(extracted)
    if not text_variants:
        return ""
    # Keep the most informative OCR result.
    return max(text_variants, key=len).strip()


def _normalize_url_filename(url: str, *, fallback: str = "web_source") -> str:
    parsed = urlparse(url)
    host = (parsed.netloc or "").strip().lower()
    path = (parsed.path or "").strip("/")
    safe_host = re.sub(r"[^a-z0-9.-]+", "_", host) or "unknown_host"
    safe_path = re.sub(r"[^a-z0-9._/-]+", "_", path.lower()).replace("/", "__")
    suffix = safe_path[:120] if safe_path else "index"
    return f"url__{safe_host}__{suffix}" or fallback


def _extract_html_title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip()


def _extract_text_from_url(url: str) -> tuple[str, str | None]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")

    try:
        response = requests.get(
            url,
            timeout=25,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            },
        )
        response.raise_for_status()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {exc}") from exc

    raw = response.content or b""
    if not raw:
        raise HTTPException(status_code=400, detail="URL returned empty body")

    content_type = (response.headers.get("content-type") or "").lower()
    is_pdf = ".pdf" in parsed.path.lower() or "application/pdf" in content_type
    if is_pdf:
        text = _extract_pdf_text(raw)
        if not text:
            raise HTTPException(status_code=400, detail="URL PDF has no readable text")
        return text, None

    # Decode as text/HTML and extract article body.
    html_or_text = response.text or _decode_uploaded_text(raw)
    if not html_or_text.strip():
        raise HTTPException(status_code=400, detail="URL has no readable text")

    looks_html = "<html" in html_or_text.lower() or "text/html" in content_type
    if looks_html:
        extracted = (trafilatura.extract(html_or_text) or "").strip()
        if extracted:
            return extracted, _extract_html_title(html_or_text) or None
        fallback = re.sub(r"<[^>]+>", " ", html_or_text)
        fallback = re.sub(r"\s+", " ", fallback).strip()
        if fallback:
            return fallback, _extract_html_title(html_or_text) or None
        raise HTTPException(status_code=400, detail="Failed to extract readable text from URL")

    text = _decode_uploaded_text(raw).strip()
    if not text:
        raise HTTPException(status_code=400, detail="URL has no readable text")
    return text, None


def _build_kb_item(
    entry: dict,
    *,
    content_length: int | None = None,
) -> VKKnowledgeBaseItemResponse:
    files: list[VKKnowledgeFileItemResponse] = []
    for doc in (entry.get("documents") or []):
        if str(doc.get("source_type") or "").strip().lower() == "text":
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
    image_caption: str | None = Form(default=None),
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
    source_type = "file"
    asset_path: str | None = None
    if extension in _IMAGE_EXTENSIONS:
        source_type = "image"
        asset_path = _save_image_asset(raw, extension)
        caption = (image_caption or "").strip()
        ocr_text = _extract_image_text(raw).strip()
        chunks: list[str] = []
        if caption:
            chunks.append(f"Описание изображения:\n{caption}")
        if ocr_text:
            chunks.append(f"Текст с изображения:\n{ocr_text}")
        text_content = "\n\n".join(chunks).strip()
        if not text_content:
            fallback_caption = Path(filename).stem.replace("_", " ").replace("-", " ").strip()
            text_content = f"Изображение: {fallback_caption or 'без подписи'}"
    else:
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
            source_type=source_type,
            mime_type=file.content_type,
            asset_path=asset_path,
            language=language,
            name=name,
            knowledge_base_id=target_kb_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    item = _build_kb_item(entry)
    return VKKnowledgeBaseUploadResponse(item=item)


@router.post(
    "/knowledge/upload-url",
    response_model=VKKnowledgeBaseUploadResponse,
    summary="Upload web page URL into SQLite knowledge base",
)
def vk_upload_knowledge_url(payload: VKKnowledgeUrlUploadRequest):
    cleaned_url = (payload.url or "").strip()
    if not cleaned_url:
        raise HTTPException(status_code=400, detail="URL is required")

    extracted_text, extracted_title = _extract_text_from_url(cleaned_url)
    text_content = extracted_text.strip()
    if not text_content:
        raise HTTPException(status_code=400, detail="URL has no readable text")

    active = _knowledge_store.get_active()
    target_kb_id = str(active.get("id") or "") if active else None
    document_title = (payload.title or "").strip() or extracted_title or cleaned_url
    try:
        entry = _knowledge_store.add_file(
            filename=_normalize_url_filename(cleaned_url),
            title=document_title,
            content=text_content,
            source_type="url",
            mime_type="text/html",
            language=payload.language,
            name=payload.name,
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
