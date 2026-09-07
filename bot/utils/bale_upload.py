from __future__ import annotations

from pathlib import Path

import aiohttp


async def send_photo_raw(
    token: str,
    chat_id: int,
    file_path: str | Path,
    caption: str = "",
) -> dict:
    url = f"https://tapi.bale.ai/bot{token}/sendPhoto"
    data = aiohttp.FormData()
    data.add_field("chat_id", str(chat_id))
    if caption:
        data.add_field("caption", caption)
    with open(file_path, "rb") as f:
        data.add_field(
            "photo",
            f,
            filename=Path(file_path).name,
            content_type="image/png",
        )
        async with aiohttp.ClientSession() as session, session.post(url, data=data) as resp:
            return await resp.json()


async def send_photo_bytes_raw(
    token: str,
    chat_id: int,
    image_bytes: bytes,
    filename: str = "image.png",
    caption: str = "",
) -> dict:
    url = f"https://tapi.bale.ai/bot{token}/sendPhoto"
    data = aiohttp.FormData()
    data.add_field("chat_id", str(chat_id))
    if caption:
        data.add_field("caption", caption)
    data.add_field(
        "photo",
        image_bytes,
        filename=filename,
        content_type="image/png",
    )
    async with aiohttp.ClientSession() as session, session.post(url, data=data) as resp:
        return await resp.json()
