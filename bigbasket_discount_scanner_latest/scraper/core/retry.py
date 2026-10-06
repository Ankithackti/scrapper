import time
import httpx


RETRYABLE_STATUS_CODES = {
    429,
    500,
    502,
    503,
    504,
}


def get_with_retry(
    client,
    url,
    attempts=3,
    backoff=5,
):

    for attempt in range(1, attempts + 1):

        try:

            response = client.get(url)

            if response.status_code not in RETRYABLE_STATUS_CODES:
                return response

            if attempt < attempts:

                time.sleep(backoff * attempt)

        except (
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.ReadError,
            httpx.RemoteProtocolError,
        ) as exc:

            if attempt == attempts:

                return None

            print(
                f"Request failed "
                f"(attempt {attempt}/{attempts}): "
                f"{type(exc).__name__} - {url}"
            )

            time.sleep(backoff * attempt)

    return None