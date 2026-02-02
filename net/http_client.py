"""
Unified async HTTP client for all parsers
"""
import asyncio
import random
import logging
import ssl
import certifi
import httpx

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

RETRY_STATUSES = {403, 429, 500, 502, 503, 504}


class HttpClient:
    """Singleton-like async HTTP client with retry logic"""

    def __init__(self, timeout: float = 20.0):
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        self._client = httpx.AsyncClient(
            headers=DEFAULT_HEADERS,
            timeout=httpx.Timeout(timeout, connect=10.0),
            follow_redirects=True,
            verify=ssl_ctx,
        )
        self._closed = False

    async def get(
        self,
        url: str,
        *,
        headers: dict | None = None,
        retries: int = 3,
        allow_insecure: bool = True,
        skip_on_304: bool = False,
    ) -> httpx.Response:
        """
        GET request with retry logic and SSL fallback.
        
        Args:
            url: Target URL
            headers: Additional/override headers
            retries: Number of retries on certain status codes
            allow_insecure: If True, retry with ssl=False on certificate errors
            skip_on_304: If True, return None for 304 Not Modified instead of raising
        
        Returns:
            httpx.Response (or None if skip_on_304=True and status is 304)
        
        Raises:
            httpx.HTTPError if all retries exhausted
        """
        merged_headers = DEFAULT_HEADERS.copy()
        if headers:
            merged_headers.update(headers)

        last_exc = None

        # Try with SSL verification first
        for attempt in range(retries + 1):
            try:
                resp = await self._client.get(url, headers=merged_headers)

                # Handle 304 Not Modified - retry with cache busting
                if resp.status_code == 304:
                    logger.debug(f"304 Not Modified for {url}, retrying with cache bust")
                    # Retry with cache busting headers
                    cache_bust_headers = merged_headers.copy()
                    cache_bust_headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                    cache_bust_headers['Pragma'] = 'no-cache'
                    try:
                        resp = await self._client.get(url, headers=cache_bust_headers)
                        return resp
                    except Exception:
                        if skip_on_304:
                            return None
                        raise

                if resp.status_code in RETRY_STATUSES:
                    raise httpx.HTTPStatusError(
                        f"HTTP {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )

                resp.raise_for_status()
                return resp

            except (ssl.SSLCertVerificationError, ssl.SSLError) as e:
                logger.warning(f"SSL error for {url}: {e}")
                if allow_insecure and attempt == 0:
                    # Retry once without SSL verification as fallback
                    try:
                        logger.info(f"Retrying {url} without SSL verification (insecure)")
                        resp = await self._client.get(
                            url, headers=merged_headers, verify=False
                        )
                        resp.raise_for_status()
                        return resp
                    except Exception as ie:
                        last_exc = ie
                        logger.error(f"Insecure retry failed for {url}: {ie}")
                else:
                    last_exc = e
            except httpx.HTTPStatusError as e:
                last_exc = e
                wait = (2 ** attempt) + random.random()
                logger.debug(
                    f"Attempt {attempt + 1}/{retries + 1} failed for {url} "
                    f"(status {e.response.status_code}), waiting {wait:.1f}s"
                )
                if attempt < retries:
                    await asyncio.sleep(wait)
            except Exception as e:
                last_exc = e
                wait = (2 ** attempt) + random.random()
                logger.debug(
                    f"Attempt {attempt + 1}/{retries + 1} failed for {url}: {e}, "
                    f"waiting {wait:.1f}s"
                )
                if attempt < retries:
                    await asyncio.sleep(wait)

        logger.error(f"All {retries + 1} retries exhausted for {url}")
        raise last_exc or httpx.RequestError(f"Failed to fetch {url}")

    async def close(self):
        """Close the HTTP client"""
        if not self._closed:
            await self._client.aclose()
            self._closed = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# Global singleton instance
_http_client = None


async def get_http_client() -> HttpClient:
    """Get or create the global HTTP client"""
    global _http_client
    if _http_client is None:
        _http_client = HttpClient()
    return _http_client


async def close_http_client():
    """Close the global HTTP client"""
    global _http_client
    if _http_client is not None:
        await _http_client.close()
        _http_client = None
