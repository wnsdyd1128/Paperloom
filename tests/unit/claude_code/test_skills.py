"""대화창의 Paperloom 스킬 원본과 `/이름` 읽기 (2026-11-19 사용자 결정 "B+C", skills.py)."""

import pytest

from paperloom.integrations.claude_code.skills import SOURCE, Skill, invoked, load

# 스킬 차례에 켤 수 있는 도구: 웹 검색과 학술 사이트 읽기뿐. PC 파일·명령·하위 에이전트 도구는 어느 스킬에도 열지 않는다
# (논문 글과 웹 글은 신뢰하지 않는 자료다)
ALLOWED_TOOLS = {"WebSearch", "WebFetch"}


def test_every_skill_is_named_after_its_folder_and_describes_itself():
    skills = load()
    assert sorted(skills) == sorted(path.parent.name for path in SOURCE.glob("*/SKILL.md")) == ["distill-paper", "explore-literature", "review-paper"]
    assert all(skill.description and skill.argument_hint for skill in skills.values())


def test_skills_open_only_web_search_and_academic_sites_and_tool_skills_wait_for_the_user():
    """도구는 실행 전에 정해지므로, 도구를 쓰는 스킬은 사용자가 `/`로 고른 차례에만 돈다(모델이 스스로 부르면 도구가 없다)."""
    for skill in load().values():
        assert set(skill.tools) <= ALLOWED_TOOLS, skill.name
        assert all(rule == "WebSearch" or rule.startswith("WebFetch(domain:") for rule in skill.allowed_tools), skill.name
        text = (SOURCE / skill.name / "SKILL.md").read_text(encoding="utf-8")
        assert ("disable-model-invocation: true" in text) == bool(skill.tools), skill.name
        assert "$ARGUMENTS" in text, skill.name  # 인자를 본문에 넣는다(넣지 않으면 Claude Code가 끝에 덧붙인다)


def test_crlf_files_are_read_too(tmp_path):
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "SKILL.md").write_bytes(
        b"---\r\nname: x\r\ndescription: d\r\nargument-hint: \"[a]\"\r\nallowed-tools: WebSearch, WebFetch(domain:arxiv.org)\r\n---\r\nbody\r\n"
    )
    assert load(tmp_path) == {"x": Skill("x", "d", "[a]", ("WebSearch", "WebFetch(domain:arxiv.org)"))}
    assert load(tmp_path)["x"].tools == ("WebSearch", "WebFetch")


@pytest.mark.parametrize(
    ("question", "name"),
    [
        ("/review-paper", "review-paper"),
        ("/review-paper Q1 · NeurIPS", "review-paper"),
        ("/distill-paper\n학부생", "distill-paper"),
        ("/review-paperX", None),  # 이름 뒤는 빈칸이나 끝이다
        ("/doctor", None),  # Paperloom 스킬이 아니다
        ("/Review-Paper", None),
        ("이 논문을 /review-paper 해 줘", None),  # 맨 앞만
        ("//review-paper", None),
    ],
)
def test_only_a_paperloom_skill_name_at_the_very_start_is_a_skill_command(question, name):
    skill = invoked(question, load())
    assert (skill.name if skill else None) == name
