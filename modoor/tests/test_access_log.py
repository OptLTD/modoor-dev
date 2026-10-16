from modoor.web.access_log import is_quiet_proxy_request, is_quiet_static_access


def test_vite_source_gets_are_quiet():
    path = "/mod/fleet/%40fs/Users/chenwen/XCode/modoor-dev/shared/widget/src/FilterPanel/index.ts"
    assert is_quiet_static_access("GET", path, 200)
    assert is_quiet_static_access("GET", "/mod/fleet/src/main.ts", 200)
    assert is_quiet_static_access("GET", "/mod/fleet/@vite/client", 200)
    assert is_quiet_static_access("GET", "/.well-known/appspecific/com.chrome.devtools.json", 404)
    assert is_quiet_static_access("GET", "/logo.png", 200)


def test_dev_proxy_httpx_lines_are_quiet():
    url = "http://127.0.0.1:5180/mod/fleet/@fs/Users/chenwen/XCode/modoor-dev/shared/hooks/src/index.ts"
    assert is_quiet_proxy_request("GET", url, 200)
    assert is_quiet_proxy_request("GET", "http://127.0.0.1:5180/mod/fleet/src/App.vue?vue&type=style", 200)
    assert not is_quiet_proxy_request("GET", url, 404)
    assert not is_quiet_proxy_request("GET", "http://example.test/api/orders", 200)


def test_api_and_failures_stay_visible():
    assert not is_quiet_static_access("GET", "/api/fleet/field-settings", 200)
    assert not is_quiet_static_access("POST", "/api/record/input", 200)
    assert not is_quiet_static_access("GET", "/mod/fleet/trailer", 200)
    assert not is_quiet_static_access(
        "GET",
        "/mod/fleet/%40fs/Users/chenwen/XCode/modoor-dev/shared/widget/src/FilterPanel/index.ts",
        404,
    )
