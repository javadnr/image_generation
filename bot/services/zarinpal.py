import logging
import httpx

logger = logging.getLogger(__name__)


class ZarinPalError(Exception):
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"ZarinPal error {code}: {message}")


class ZarinPalClient:
    def __init__(self, base_url: str, project_id: int) -> None:
        self._base_url = base_url.rstrip("/")
        self._project_id = project_id

    async def request_payment(self, amount_toman: int, description: str) -> tuple[str, str]:
        amount_rial = amount_toman * 10
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            resp = await client.post(
                f"{self._base_url}/api/v1/create",
                json={"amount": amount_rial, "project_id": self._project_id},
            )
            resp.raise_for_status()
            data = resp.json()

        payment_link = data.get("payment_link", "")
        if not payment_link:
            raise ZarinPalError(0, "No payment_link in response")

        authority = payment_link.rstrip("/").rsplit("/", 1)[-1]
        return authority, payment_link

    async def verify_payment(self, authority: str, amount_toman: int) -> tuple[int, str]:
        amount_rial = amount_toman * 10
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            resp = await client.post(
                f"{self._base_url}/api/v1/verify",
                json={"authority": authority, "amount": amount_rial},
            )
            data = resp.json()

        if resp.status_code == 200:
            return data.get("code", -51), data.get("status", "unknown")
        if resp.status_code == 402:
            return -52, data.get("detail", "Payment unsuccessful")
        else:
            raise ZarinPalError(resp.status_code, data.get("detail", "Unknown error"))
