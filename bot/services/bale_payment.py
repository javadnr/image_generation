import logging

import httpx

logger = logging.getLogger(__name__)


class BalePaymentError(Exception):
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"Bale payment error {code}: {message}")


class BalePaymentProvider:
    def __init__(self, bot_token: str, provider_token: str) -> None:
        self._bot_token = bot_token
        self._provider_token = provider_token
        self._base_url = f"https://tapi.bale.ai/bot{bot_token}"

    async def send_invoice(
        self,
        chat_id: int,
        title: str,
        description: str,
        payload: str,
        prices: list[dict],
        photo_url: str | None = None,
    ) -> dict:
        url = f"{self._base_url}/sendInvoice"
        data: dict = {
            "chat_id": chat_id,
            "title": title,
            "description": description,
            "payload": payload,
            "provider_token": self._provider_token,
            "prices": prices,
        }
        if photo_url:
            data["photo_url"] = photo_url

        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            resp = await client.post(url, json=data)
            result = resp.json()
            if not result.get("ok"):
                error_code = result.get("error_code", 0)
                desc = result.get("description", "Unknown error")
                raise BalePaymentError(error_code, desc)
            return result.get("result", {})

    async def answer_pre_checkout(
        self,
        pre_checkout_query_id: str,
        ok: bool = True,
        error_message: str | None = None,
    ) -> dict:
        url = f"{self._base_url}/answerPreCheckoutQuery"
        data: dict = {
            "pre_checkout_query_id": pre_checkout_query_id,
            "ok": ok,
        }
        if error_message:
            data["error_message"] = error_message

        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            resp = await client.post(url, json=data)
            result = resp.json()
            if not result.get("ok"):
                error_code = result.get("error_code", 0)
                desc = result.get("description", "Unknown error")
                raise BalePaymentError(error_code, desc)
            return result
