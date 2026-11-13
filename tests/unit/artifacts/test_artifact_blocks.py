"""답 Markdown 안의 아티팩트 찾기 (paperloom.artifacts.blocks). 웹이 답을 그릴 때의 규칙(apps/web/src/features/artifacts/artifact.test.ts)과 같다."""

from paperloom.artifacts.blocks import Block, artifacts_in, without_artifacts


def test_artifact_blocks_are_read_in_order_with_their_fields():
    markdown = (
        "그림을 만들었습니다.\n\n"
        '```artifact type="code" language="python" title="합 계산"\nprint(1)\n```\n\n'
        '```artifact type="html" title=" 그림 " language="x"\n<p>\n```\n'
        '```artifact type="svg"\n<svg/>\n```\n'
    )

    assert artifacts_in(markdown) == [
        Block("code", "합 계산", "python", "print(1)"),
        Block("html", "그림", None, "<p>"),  # 값의 앞뒤 공백을 떼고, code만 언어가 있다
        Block("svg", "그림", None, "<svg/>"),  # 제목이 없으면 종류의 이름
    ]


def test_blocks_without_a_known_type_are_not_artifacts():
    markdown = '```artifact\nx\n```\n```artifact title="제목"\nx\n```\n```artifact type="pdf"\nx\n```\n```Artifact type="html"\nx\n```\n'
    assert artifacts_in(markdown) == []


def test_plain_blocks_that_open_as_they_are_are_artifacts_too():
    page = '<!DOCTYPE html>\n<html lang="ko">\n<head><title> Capuchin 발표 예상 질문 </title></head>\n<body></body>\n</html>'
    markdown = f"```html\n{page}\n```\n```HTML\n\n<html><body>x</body></html>\n```\n```svg\n<svg viewBox=\"0 0 1 1\"></svg>\n```\n```mermaid\nflowchart LR\n  A --> B\n```\n"

    assert artifacts_in(markdown) == [
        Block("html", "Capuchin 발표 예상 질문", None, page),  # 제목은 문서의 <title>
        Block("html", "HTML 페이지", None, "\n<html><body>x</body></html>"),
        Block("svg", "그림", None, '<svg viewBox="0 0 1 1"></svg>'),
        Block("mermaid", "다이어그램", None, "flowchart LR\n  A --> B"),
    ]


def test_fragments_other_languages_and_empty_blocks_stay_code():
    markdown = "".join(
        f"```{language}\n{body}\n```\n"
        for language, body in [
            ("html", '<div class="card">예</div>'), ("html", "<htmlx>"), ("svg", "<path d='M0 0'/>"), ("xml", "<svg></svg>"),
            ("mermaid", ""), ("python", "<!doctype html>"), ("", "<svg></svg>"),
        ]
    )
    assert artifacts_in(markdown) == []


def test_fences_follow_commonmark():
    markdown = (
        '````artifact type="markdown" title="정리"\n# 정리\n```python\nprint("안")\n```\n````\n'  # 안에 ```가 있으면 바깥을 더 길게
        '~~~artifact\ttype="react"\nexport default () => null;\n~~~\n'  # 물결 울타리, 언어 뒤가 탭
        '   ```artifact type="code" language="c"\n   int x;\n     y;\n   ```\n'  # 세 칸까지 들인 울타리는 그만큼 뗀다
        '    ```artifact type="svg"\n    <svg/>\n    ```\n'  # 네 칸이면 들여 쓴 코드다
        '```artifact type="html" `x`\n'  # 백틱 울타리의 정보 글에 백틱이 있으면 울타리가 아니다(그 줄은 글이다)
        '```artifact type="html" title="끝까지"\n<p>닫지 않음\n'  # 닫는 줄이 없으면 답 끝까지
    )

    assert artifacts_in(markdown) == [
        Block("markdown", "정리", None, '# 정리\n```python\nprint("안")\n```'),
        Block("react", "React 화면", None, "export default () => null;"),
        Block("code", "코드", "c", "int x;\n  y;"),
        Block("html", "끝까지", None, "<p>닫지 않음"),
    ]


def test_without_artifacts_leaves_one_line_per_artifact_and_keeps_other_code():
    markdown = (
        "앞 글\n\n"
        '```artifact type="html" title="캐시 그림"\n<html>\n```\n\n'
        "```python\nprint(1)\n```\n"
        '````artifact type="markdown"\n```\n안\n```\n````\n'
        "뒤 글\n"
    )

    assert without_artifacts(markdown) == "앞 글\n\n[아티팩트: 캐시 그림]\n\n```python\nprint(1)\n```\n[아티팩트: 문서]\n뒤 글"
    assert without_artifacts("아티팩트 없음") == "아티팩트 없음"
