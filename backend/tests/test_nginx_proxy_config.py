from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_web_proxy_resolves_recreated_api_containers_dynamically() -> None:
    config = (ROOT / "frontend/nginx.t29.conf").read_text(encoding="utf-8")

    assert "resolver 127.0.0.11" in config
    assert config.count("proxy_pass $api_upstream$request_uri;") == 2
    assert "proxy_pass http://api:18081;" not in config
