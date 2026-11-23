"""Exceptions raised by the Bluefors Temperature Controller client."""

from __future__ import annotations

from typing import Any, Optional


class TCError(Exception):
    """Base class for every error raised by this package."""


class TCConnectionError(TCError):
    """The Temperature Controller could not be reached over the network."""


class TCTimeoutError(TCError):
    """The Temperature Controller did not answer, or sent no data, in time."""


class TCNoDataError(TCError):
    """The request succeeded, but the Temperature Controller had no matching data."""


class TCWarning(UserWarning):
    """The Temperature Controller accepted a request that probably will not work as intended.

    For example, a PID loop on a channel that measures no temperature. Filter
    it like any other warning, for example with ``warnings.simplefilter``.
    """


class TCRequestError(TCError):
    """The Temperature Controller rejected a request.

    Attributes:
        endpoint: API endpoint that was called, for example ``"heater/update"``.
        payload: JSON body that was sent, if any.
        message: Error text reported by the Temperature Controller.
        response: Full decoded response, if the reply was JSON.
    """

    def __init__(
        self,
        endpoint: str,
        message: str,
        payload: Optional[dict[str, Any]] = None,
        response: Optional[dict[str, Any]] = None,
    ) -> None:
        self.endpoint = endpoint
        self.message = message
        self.payload = payload
        self.response = response
        super().__init__(f"{endpoint}: {message}")

    @classmethod
    def from_response(
        cls, endpoint: str, payload: Optional[dict[str, Any]], response: dict[str, Any]
    ) -> TCRequestError:
        """Build an error from an ``"status": "ERROR"`` reply.

        Software 2.x replies with ``error_msg``; the API technical reference
        describes an ``error`` object with ``code``, ``message`` and ``details``.
        Both forms are accepted.
        """
        error = response.get("error")
        if isinstance(error, dict):
            parts = [str(error.get("message") or "request failed")]
            if error.get("details"):
                parts.append(str(error["details"]))
            if error.get("code") is not None:
                parts.append(f"(code {error['code']})")
            message = " ".join(parts)
        else:
            raw = response.get("error_msg", "request failed")
            message = f"request rejected (HTTP {raw})" if isinstance(raw, int) else str(raw)
        return cls(endpoint, message, payload=payload, response=response)
