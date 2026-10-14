import httpx
import pytest

from app.services.air_quality import OpenWeatherMapProvider, ProviderError

GOOD_PAYLOAD = {
    "coord": {"lon": 69.2, "lat": 41.3},
    "list": [
        {
            "main": {"aqi": 3},
            "components": {"co": 300.0, "pm2_5": 48.0, "pm10": 71.0, "o3": 20.0},
            "dt": 1760095800,
        }
    ],
}


def make_provider(handler, *, retries=3, api_key="k") -> tuple[OpenWeatherMapProvider, list]:
    calls: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return handler(request, len(calls))

    client = httpx.AsyncClient(transport=httpx.MockTransport(wrapped))
    provider = OpenWeatherMapProvider(api_key, client=client, retries=retries, backoff=0)
    return provider, calls


async def test_success_parses_and_computes_aqi():
    provider, calls = make_provider(lambda req, n: httpx.Response(200, json=GOOD_PAYLOAD))
    reading = await provider.fetch(41.3, 69.2)

    assert reading.aqi == 132  # OWM ning 1-5 shkalasi emas, PM2.5 dan hisoblangan AQI
    assert reading.pm2_5 == 48.0 and reading.pm10 == 71.0
    assert reading.recorded_at.tzinfo is not None
    assert reading.source == "openweathermap"
    assert calls[0].url.params["lat"] == "41.3" and calls[0].url.params["appid"] == "k"


async def test_retries_server_errors_then_succeeds():
    def handler(req, n):
        return httpx.Response(503) if n < 3 else httpx.Response(200, json=GOOD_PAYLOAD)

    provider, calls = make_provider(handler)
    assert (await provider.fetch(41.3, 69.2)).aqi == 132
    assert len(calls) == 3


async def test_retries_network_errors():
    def handler(req, n):
        if n == 1:
            raise httpx.ConnectTimeout("timeout", request=req)
        return httpx.Response(200, json=GOOD_PAYLOAD)

    provider, calls = make_provider(handler)
    assert (await provider.fetch(41.3, 69.2)).aqi == 132
    assert len(calls) == 2


async def test_gives_up_after_all_retries():
    provider, calls = make_provider(lambda req, n: httpx.Response(500), retries=3)
    with pytest.raises(ProviderError):
        await provider.fetch(41.3, 69.2)
    assert len(calls) == 3


async def test_invalid_key_is_not_retried():
    provider, calls = make_provider(lambda req, n: httpx.Response(401, json={"cod": 401}))
    with pytest.raises(ProviderError, match="kalit"):
        await provider.fetch(41.3, 69.2)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json={"list": []}),
        httpx.Response(200, json={"unexpected": True}),
        httpx.Response(200, content=b"not json"),
        httpx.Response(200, json={"list": [{"components": {"co": 1}, "dt": 1}]}),  # PM yo'q
    ],
)
async def test_malformed_response_raises_provider_error(response):
    provider, _ = make_provider(lambda req, n: response)
    with pytest.raises(ProviderError):
        await provider.fetch(41.3, 69.2)


async def test_missing_api_key():
    provider, calls = make_provider(lambda req, n: httpx.Response(200, json=GOOD_PAYLOAD), api_key="")
    with pytest.raises(ProviderError, match="OWM_API_KEY"):
        await provider.fetch(41.3, 69.2)
    assert calls == []
