from __future__ import annotations

import re
from xml.etree import ElementTree

import magic

CONTENT_TYPE_ICO = "image/x-icon"
CONTENT_TYPE_JPG = "image/jpeg"
CONTENT_TYPE_PNG = "image/png"
CONTENT_TYPE_SVG = "image/svg+xml"

CONTENT_TYPE_PDF = "application/pdf"

CONTENT_TYPE_MP4 = "video/mp4"
CONTENT_TYPE_QUICKTIME = "video/quicktime"
CONTENT_TYPE_WEBM = "video/webm"

SVG_XML_CONTENT_TYPES = {
    CONTENT_TYPE_SVG,
    "application/xml",
    "text/plain",
    "text/xml",
}
VIDEO_CONTENT_TYPES = {
    CONTENT_TYPE_MP4,
    CONTENT_TYPE_QUICKTIME,
    CONTENT_TYPE_WEBM,
}

_FORBIDDEN_SVG_ELEMENTS = {
    "embed",
    "foreignobject",
    "iframe",
    "object",
    "script",
}
_SVG_URL_RE = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE)


def get_content_type(file):
    if hasattr(file, "temporary_file_path"):
        content_type = magic.from_file(file.temporary_file_path(), mime=True)
    else:
        # libmagic only needs the beginning of the file. Reading a complete video
        # here would needlessly load hundreds of megabytes into memory.
        content_type = magic.from_buffer(file.read(8192), mime=True)

    if hasattr(file, "seek") and callable(file.seek):
        file.seek(0)

    return content_type


def read_file(file, max_bytes: int) -> bytes:
    """Read a bounded upload and restore its cursor for Django storage."""
    size = getattr(file, "size", None)
    if size is not None and size > max_bytes:
        raise ValueError(f"File exceeds the limit of {max_bytes} bytes.")

    data = file.read(max_bytes + 1)
    if hasattr(file, "seek") and callable(file.seek):
        file.seek(0)
    if len(data) > max_bytes:
        raise ValueError(f"File exceeds the limit of {max_bytes} bytes.")
    return data


def validate_safe_svg(file, max_bytes: int) -> None:
    """Reject executable or externally-referenced content from SVG uploads."""
    data = read_file(file, max_bytes)
    lowered = data.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise ValueError("SVG declarations and entities are not allowed.")

    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise ValueError("Invalid or corrupted SVG image.") from exc

    if _local_name(root.tag) != "svg":
        raise ValueError("The XML root element must be <svg>.")

    for element in root.iter():
        name = _local_name(element.tag)
        if name in _FORBIDDEN_SVG_ELEMENTS:
            raise ValueError(f"SVG element <{name}> is not allowed.")

        for raw_name, raw_value in element.attrib.items():
            attribute = _local_name(raw_name)
            value = raw_value.strip()
            if attribute.startswith("on"):
                raise ValueError("SVG event attributes are not allowed.")
            if attribute in {"href", "src"} and not _safe_svg_reference(value):
                raise ValueError("External SVG references are not allowed.")
            if attribute == "style":
                _validate_svg_style(value)

        if name == "style" and element.text:
            _validate_svg_style(element.text)


def _local_name(value: str) -> str:
    return value.rsplit("}", 1)[-1].lower()


def _safe_svg_reference(value: str) -> bool:
    lowered = value.lower()
    return (
        not value
        or value.startswith("#")
        or lowered.startswith("data:image/png;base64,")
        or lowered.startswith("data:image/jpeg;base64,")
        or lowered.startswith("data:image/webp;base64,")
    )


def _validate_svg_style(value: str) -> None:
    lowered = value.lower()
    if "@import" in lowered or "javascript:" in lowered:
        raise ValueError("External or executable SVG styles are not allowed.")
    for match in _SVG_URL_RE.finditer(value):
        if not match.group(2).strip().startswith("#"):
            raise ValueError("External SVG style references are not allowed.")
