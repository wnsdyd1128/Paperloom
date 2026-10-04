"""브리지가 Paperloom Core의 웹 REST를 부르는 클라이언트. 표준 라이브러리만 쓴다.

Core는 이 PC의 loopback에서만 열려 있다(IMPL §3 local). 다른 컴퓨터의 평문 주소는 쓰지 않는다.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from urllib.parse import quote

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


class CoreUnavailable(Exception):
    """Paperloom Core에 연결할 수 없다."""


class CoreRefused(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.status = status
        self.code = code
        self.message = message


class CoreClient:
    def __init__(self, base_url: str, timeout_seconds: float = 60) -> None:
        url = urllib.parse.urlsplit(base_url)
        if url.scheme not in ("http", "https") or (url.scheme == "http" and url.hostname not in LOCAL_HOSTS):
            raise ValueError("PAPERLOOM_URL은 이 컴퓨터의 주소(http://127.0.0.1:…)이거나 https여야 합니다.")
        self.base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    def packet(self, packet_id: str) -> dict | None:
        try:
            return json.loads(self._request("GET", f"/api/v1/context-packets/{quote(packet_id, safe='')}"))
        except CoreRefused as refused:
            if refused.status == 404:
                return None
            raise

    def markdown(self, packet_id: str) -> str:
        """이미지를 메시지에 함께 붙이는 대화용 글."""
        return self._request("GET", f"/api/v1/context-packets/{quote(packet_id, safe='')}/export.md?images=attached").decode("utf-8")

    def image(self, path: str) -> bytes:
        """packet 근거의 영역 이미지 주소(/api/v1/anchors/…/image)만 받는다."""
        if not path.startswith("/api/v1/anchors/"):
            raise ValueError(path)
        return self._request("GET", path)

    def hand_off(self, packet_id: str) -> dict:
        body = {"status": "HANDED_OFF", "handoff_method": "claude_code"}
        return json.loads(self._request("PATCH", f"/api/v1/context-packets/{quote(packet_id, safe='')}", body))

    def preferences(self) -> dict:
        """사용자 설정 (U6, A3). 차례마다 읽는다."""
        return json.loads(self._request("GET", "/api/v1/settings"))

    def page_text(self, version_id: str, page_index: int) -> dict:
        """쪽의 문단(읽는 차례). 쪽 번역(U7)이 읽는다."""
        return json.loads(self._request("GET", f"/api/v1/versions/{quote(version_id, safe='')}/pages/{page_index}"))

    def page_translation(self, version_id: str, page_index: int, language: str) -> dict | None:
        """저장된 쪽 번역. 번역하지 않았으면(또는 다시 추출로 글이 바뀌었으면) None."""
        try:
            return json.loads(self._request("GET", self._translation_path(version_id, page_index, language)))
        except CoreRefused as refused:
            if refused.code == "NOT_TRANSLATED":
                return None
            raise

    def save_page_translation(self, version_id: str, page_index: int, language: str, model: str | None, blocks: list[dict]) -> dict:
        return json.loads(self._request("PUT", self._translation_path(version_id, page_index, language), {"model": model, "blocks": blocks}))

    @staticmethod
    def _translation_path(version_id: str, page_index: int, language: str) -> str:
        return f"/api/v1/versions/{quote(version_id, safe='')}/pages/{page_index}/translations/{quote(language, safe='')}"

    def session_answers(self, session_id: str) -> list[dict]:
        """이 브리지가 저장한(claude_code) 그 대화의 답변들."""
        query = urllib.parse.urlencode({"session_id": session_id, "origin": "claude_code", "limit": 200})
        return json.loads(self._request("GET", f"/api/v1/answers?{query}"))["answers"]

    def save_answer(
        self,
        packet_id: str,
        prompt: str,
        markdown: str,
        session_id: str,
        context: tuple[int | None, int | None] = (None, None),
        message_id: str | None = None,
    ) -> dict:
        """context: 차례 끝의 컨텍스트 길이와 모델의 창 크기, message_id: 차례 끝 Claude Code 메시지 ID(모르면 None)."""
        tokens, window = context
        body = {"markdown": markdown, "prompt": prompt, "session_id": session_id}
        optional = (("context_tokens", tokens), ("context_window", window), ("message_id", message_id))
        body |= {key: value for key, value in optional if value is not None}
        return json.loads(self._request("POST", f"/api/v1/context-packets/{quote(packet_id, safe='')}/answers", body))

    def _request(self, method: str, path: str, body: dict | None = None) -> bytes:
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"} if data is not None else {}
        request = urllib.request.Request(self.base_url + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            try:
                envelope = json.loads(error.read())
                raise CoreRefused(error.code, envelope["code"], envelope["message"]) from None
            except (ValueError, KeyError):
                raise CoreRefused(error.code, f"HTTP_{error.code}", "Paperloom이 요청을 거부했습니다.") from None
        except (urllib.error.URLError, ConnectionError, TimeoutError) as error:
            raise CoreUnavailable(str(error)) from None
