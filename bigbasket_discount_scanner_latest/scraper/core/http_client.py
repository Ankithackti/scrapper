import asyncio
import httpx


class AsyncHttpClient:
    """Small async HTTP client with bounded concurrency and connection reuse."""

    def __init__(self, delay=0.5, timeout=30.0, concurrency=8):
        self.delay = max(0.0, float(delay))
        self.timeout = float(timeout)
        self.semaphore = asyncio.Semaphore(max(1, int(concurrency)))
        self.client = None
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/153.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
        }

    async def start(self):
        if self.client is None:
            timeout = httpx.Timeout(
                connect=10.0,
                read=self.timeout,
                write=10.0,
                pool=10.0,
            )
            limits = httpx.Limits(
                max_connections=max(8, self.semaphore._value * 2),
                max_keepalive_connections=max(4, self.semaphore._value),
            )
            self.client = httpx.AsyncClient(
                follow_redirects=True,
                timeout=timeout,
                limits=limits,
                headers=self.headers,
                http2=False,
            )

    async def get(self, url, retries=2):
        await self.start()

        async with self.semaphore:
            for attempt in range(retries + 1):
                try:
                    if self.delay:
                        await asyncio.sleep(self.delay)

                    response = await self.client.get(url)

                    # Do not retry access-control responses. They are not transient.
                    if response.status_code in {403, 404}:
                        return response

                    if response.status_code not in {429, 500, 502, 503, 504}:
                        return response

                    if attempt >= retries:
                        return response

                except (
                    httpx.TimeoutException,
                    httpx.ConnectError,
                    httpx.ReadError,
                    httpx.RemoteProtocolError,
                ) as exc:
                    if attempt >= retries:
                        print(f"REQUEST FAILED: {url} -> {type(exc).__name__}")
                        return None

                await asyncio.sleep(1.0 * (attempt + 1))

        return None

    async def close(self):
        if self.client is not None:
            await self.client.aclose()
            self.client = None
