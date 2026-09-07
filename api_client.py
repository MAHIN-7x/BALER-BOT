import aiohttp
import json

BASE_URL = "https://hero-sms.com/stubs/handler_api.php"

class HeroSMSClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def _get(self, action: str, **kwargs):
        params = {"api_key": self.api_key, "action": action}
        params.update(kwargs)
        async with aiohttp.ClientSession() as session:
            async with session.get(BASE_URL, params=params) as response:
                text = await response.text()
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text

    async def get_balance(self):
        res = await self._get("getBalance")
        if isinstance(res, str) and res.startswith("ACCESS_BALANCE:"):
            try:
                return float(res.split(":")[1])
            except (IndexError, ValueError):
                return None
        return None

    async def get_prices(self, country: int = None, service: str = None):
        params = {}
        if country is not None:
            params["country"] = country
        if service is not None:
            params["service"] = service
        return await self._get("getPrices", **params)

    async def get_number(self, service: str, country: int, max_price: float = None):
        params = {"service": service, "country": country}
        if max_price is not None:
            params["maxPrice"] = max_price
        return await self._get("getNumberV2", **params)

    async def get_status(self, activation_id: str):
        return await self._get("getStatus", id=activation_id)

    async def set_status(self, activation_id: str, status: int):
        return await self._get("setStatus", id=str(activation_id), status=status)

    async def get_active_activations(self):
        return await self._get("getActiveActivations")
