"""Gateway error taxonomy (QA11) with leak-free public messages.

Every failure the gateway can produce is a :class:`GatewayError` with a fixed
category. Messages are fixed strings: raw upstream bodies, exception text,
cookies and PATs never travel into logs, API payloads or UI text.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class GatewayErrorCategory(StrEnum):
    CONFIG = "CONFIG"
    UNSUPPORTED_OPERATION = "UNSUPPORTED_OPERATION"
    VALIDATION = "VALIDATION"
    AUTH = "AUTH"
    RATE = "RATE"
    SERVER = "SERVER"
    TIMEOUT = "TIMEOUT"
    CANCEL = "CANCEL"
    OUTPUT_LIMIT = "OUTPUT_LIMIT"
    UNKNOWN = "UNKNOWN"


PUBLIC_MESSAGES: dict[GatewayErrorCategory, str] = {
    GatewayErrorCategory.CONFIG: "AI 网关未启用或缺少必要配置",
    GatewayErrorCategory.UNSUPPORTED_OPERATION: "不支持的 AI 操作",
    GatewayErrorCategory.VALIDATION: "AI 请求或返回不符合冻结契约",
    GatewayErrorCategory.AUTH: "上游鉴权失败",
    GatewayErrorCategory.RATE: "上游限流",
    GatewayErrorCategory.SERVER: "上游服务错误",
    GatewayErrorCategory.TIMEOUT: "上游调用超时",
    GatewayErrorCategory.CANCEL: "调用已取消",
    GatewayErrorCategory.OUTPUT_LIMIT: "上游返回超过允许大小",
    GatewayErrorCategory.UNKNOWN: "上游调用失败",
}


@dataclass(frozen=True)
class GatewayError:
    category: GatewayErrorCategory
    reason_code: str
    message: str | None = None
    upstream_status: int | None = None

    @property
    def public_message(self) -> str:
        return self.message or PUBLIC_MESSAGES[self.category]

    def to_public(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "category": self.category.value,
            "reason_code": self.reason_code,
            "message": self.public_message,
        }
        if self.upstream_status is not None:
            payload["upstream_status"] = self.upstream_status
        return payload


def classify_upstream_status(status_code: int) -> GatewayErrorCategory | None:
    """Map an HTTP status to the QA11 taxonomy. 2xx means success (None)."""

    if 200 <= status_code < 300:
        return None
    if status_code in (401, 403):
        return GatewayErrorCategory.AUTH
    if status_code == 429:
        return GatewayErrorCategory.RATE
    if 500 <= status_code < 600:
        return GatewayErrorCategory.SERVER
    return GatewayErrorCategory.UNKNOWN


def error_from_status(status_code: int) -> GatewayError:
    category = classify_upstream_status(status_code) or GatewayErrorCategory.UNKNOWN
    return GatewayError(category, f"UPSTREAM_{status_code}", upstream_status=status_code)
