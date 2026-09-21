import pytest
import responses

from core.utils.http import HttpError, NSEHttpClient, PlainHttpClient


@responses.activate
def test_plain_client_basic_get():
    responses.add(responses.GET, "https://example.com/x",
                  body=b"hello", status=200)
    c = PlainHttpClient("UA", delay_ms=0)
    assert c.get("https://example.com/x") == b"hello"

@responses.activate
def test_plain_client_raises_on_4xx():
    responses.add(responses.GET, "https://example.com/y",
                  body=b"nope", status=404)
    c = PlainHttpClient("UA", delay_ms=0)
    with pytest.raises(HttpError):
        c.get("https://example.com/y")

@responses.activate
def test_nse_client_bootstraps_then_fetches():
    responses.add(responses.GET, "https://www.nseindia.com/",
                  body=b"<html>", status=200)
    responses.add(responses.GET, "https://example.com/api",
                  body=b"payload", status=200)
    c = NSEHttpClient("UA", delay_ms=0)
    assert c.get("https://example.com/api") == b"payload"
