"""最小化的 MCP Streamable HTTP 客户端，仅依赖标准库。

只实现本项目用到的部分：initialize → tools/list / tools/call。
服务端既可能直接返回 application/json，也可能返回 text/event-stream，两种都兼容。
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .paths import ENV_FILES

DEFAULT_URL = "https://mcp.mcd.cn"
PROTOCOL_VERSION = "2025-03-26"
CLIENT_INFO = {"name": "mcd-persona-card", "version": "0.1.0"}


class MCPError(RuntimeError):
    pass


def load_token(env_files: Sequence[Path] = ENV_FILES) -> str:
    """优先读取环境变量 MCD_MCP_TOKEN，其次依次查找 .env 文件。"""
    token = os.environ.get("MCD_MCP_TOKEN", "").strip()
    if token:
        return token
    for env_file in env_files:
        if not env_file.is_file():
            continue
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "MCD_MCP_TOKEN" and value.strip():
                return value.strip().strip('"').strip("'")
    raise MCPError(
        "未找到 MCD_MCP_TOKEN。请先在 https://open.mcd.cn/mcp 申请 Token，然后设置环境变量 "
        "export MCD_MCP_TOKEN=你的Token，或写入 ~/.mcd-persona-card/.env（也可以用 --demo 体验演示数据）"
    )


class MCPClient:
    def __init__(self, token: str, url: str = DEFAULT_URL, timeout: float = 30.0):
        self.url = url
        self.token = token
        self.timeout = timeout
        self.session_id: Optional[str] = None
        self._next_id = 1
        self._initialized = False

    # ---- 底层传输 ----

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {self.token}",
            "User-Agent": f"{CLIENT_INFO['name']}/{CLIENT_INFO['version']}",
        }
        if self._initialized:
            headers["MCP-Protocol-Version"] = PROTOCOL_VERSION
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        return headers

    def _post(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.url, data=body, headers=self._headers(), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                sid = resp.headers.get("Mcp-Session-Id")
                if sid:
                    self.session_id = sid
                content_type = resp.headers.get("Content-Type", "")
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise MCPError("401：MCP Token 无效、已过期或未提供") from None
            if e.code == 429:
                raise MCPError("429：请求过于频繁（每分钟上限 600 次），请稍后再试") from None
            raise MCPError(f"HTTP {e.code}：{e.read().decode('utf-8', 'replace')[:300]}") from None
        except urllib.error.URLError as e:
            raise MCPError(f"无法连接 {self.url}：{e.reason}") from None

        if "id" not in payload:  # 通知，没有响应体
            return None
        message = self._parse_response(raw, content_type, payload["id"])
        if "error" in message:
            err = message["error"]
            raise MCPError(f"MCP 错误 {err.get('code')}：{err.get('message')}")
        return message.get("result", {})

    @staticmethod
    def _parse_response(raw: str, content_type: str, req_id: int) -> Dict[str, Any]:
        if "text/event-stream" in content_type:
            candidates = []
            data_lines: List[str] = []
            for line in raw.splitlines() + [""]:
                if line.startswith("data:"):
                    data_lines.append(line[5:].lstrip())
                elif line == "" and data_lines:
                    candidates.append("\n".join(data_lines))
                    data_lines = []
            for chunk in candidates:
                try:
                    msg = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                if isinstance(msg, dict) and msg.get("id") == req_id:
                    return msg
            raise MCPError("SSE 响应中没有找到对应请求的结果")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            raise MCPError(f"无法解析服务端响应：{raw[:300]}") from None

    def _request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        req_id = self._next_id
        self._next_id += 1
        payload: Dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            payload["params"] = params
        return self._post(payload) or {}

    # ---- MCP 方法 ----

    def initialize(self) -> Dict[str, Any]:
        result = self._request(
            "initialize",
            {"protocolVersion": PROTOCOL_VERSION, "capabilities": {}, "clientInfo": CLIENT_INFO},
        )
        self._initialized = True
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return result

    def _ensure_init(self) -> None:
        if not self._initialized:
            self.initialize()

    def list_tools(self) -> List[Dict[str, Any]]:
        self._ensure_init()
        return self._request("tools/list").get("tools", [])

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """返回原始 tools/call 结果（含 content / structuredContent / isError）。"""
        self._ensure_init()
        return self._request("tools/call", {"name": name, "arguments": arguments or {}})

    def call_tool_data(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        """调用工具并尽量把结果解析成 Python 对象。"""
        result = self.call_tool(name, arguments)
        if result.get("isError"):
            raise MCPError(f"工具 {name} 返回错误：{extract_text(result)[:300]}")
        return result_to_data(result)


def extract_text(result: Dict[str, Any]) -> str:
    parts = [c.get("text", "") for c in result.get("content", []) if c.get("type") == "text"]
    return "\n".join(parts)


def result_to_data(result: Dict[str, Any]) -> Any:
    if result.get("structuredContent") is not None:
        return result["structuredContent"]
    text = extract_text(result)
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text
