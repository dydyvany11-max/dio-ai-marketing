from __future__ import annotations

import io
from dataclasses import dataclass

import qrcode


@dataclass
class QRLoginState:
    pending: bool = False
    expires_at: str | None = None
    error: str | None = None


class QRCodeRenderer:
    def render_png(self, content: str) -> bytes:
        qr = qrcode.QRCode(box_size=10, border=2)
        qr.add_data(content)
        qr.make(fit=True)

        image = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer.read()
