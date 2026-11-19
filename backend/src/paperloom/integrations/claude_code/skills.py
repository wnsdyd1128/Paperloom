"""대화창의 Paperloom 스킬: Claude Code 스킬(SKILL.md)을 그대로 쓴다 (2026-11-19 사용자 결정 "B+C", ADR 0003).

- 원본은 이 패키지의 skills/<이름>/SKILL.md다. 브리지가 켜질 때 작업 폴더의 .claude/skills에 옮긴다(install). 그 폴더는
  Paperloom이 관리한다: 원본에 없는 스킬은 지운다.
- 작업 폴더의 .claude/settings.json(project 설정: 대화는 `--setting-sources project`라 이 설정만 읽는다)으로 Claude Code에
  딸린 skill·workflow와 내장 플러그인 skill을 끄고, auto memory와 skill 안 셸 실행을 끈다(SETTINGS, 2026-11-19 확인 실행).
- 사용자가 질문 맨 앞에 `/이름 인자`를 쓰면 그 스킬 차례다(invoked). 그 차례에만 스킬 frontmatter의 allowed-tools(웹 검색,
  학술 사이트로 한정한 WebFetch)를 켜고 묻지 않고 허락한다. 도구를 쓰는 스킬은 모델이 스스로 부르지 못하게 둔다
  (disable-model-invocation): 도구는 실행 전에 정해지므로, 모델이 고른 차례에는 그 도구가 없다.
"""

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import yaml

SOURCE = Path(__file__).resolve().parent / "skills"

# Claude Code 2.1.305에서 disableBundledSkills를 켜도 남는 내장 플러그인 skill (2026-11-19 확인 실행의 init 사건)
BUILTIN_PLUGIN_SKILLS = ("design", "doctor", "plugin-authoring")
SETTINGS = {
    "disableBundledSkills": True,
    "skillOverrides": {name: "off" for name in BUILTIN_PLUGIN_SKILLS},
    "autoMemoryEnabled": False,  # 켜 두면 ~/.claude/projects/<작업 폴더>/memory를 만들고 지시에 넣는다
    "disableSkillShellExecution": True,
}

COMMAND = re.compile(r"/([a-z0-9][a-z0-9-]*)(?=\s|$)")


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    argument_hint: str
    allowed_tools: tuple[str, ...]  # 권한 규칙(WebSearch, WebFetch(domain:arxiv.org) …)

    @property
    def tools(self) -> tuple[str, ...]:
        """--tools에 넣을 도구 이름(규칙의 괄호 앞, 차례대로 한 번씩)."""
        return tuple(dict.fromkeys(rule.split("(", 1)[0] for rule in self.allowed_tools))


def load(source: Path = SOURCE) -> dict[str, Skill]:
    """원본 스킬들(이름 → Skill), 이름 차례."""
    skills = {}
    for path in sorted(source.glob("*/SKILL.md")):
        meta = _frontmatter(path.read_text(encoding="utf-8"))
        rules = tuple(rule.strip() for rule in str(meta.get("allowed-tools") or "").split(",") if rule.strip())
        skills[meta["name"]] = Skill(meta["name"], meta["description"], meta.get("argument-hint") or "", rules)
    return skills


def install(work_dir: Path, source: Path = SOURCE) -> None:
    """작업 폴더에 project 설정과 원본 스킬을 둔다. 원본에 없는 스킬은 지운다."""
    claude = work_dir / ".claude"
    target = claude / "skills"
    claude.mkdir(parents=True, exist_ok=True)
    (claude / "settings.json").write_text(json.dumps(SETTINGS, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    if target.exists():
        shutil.rmtree(target)
    for skill in sorted(source.glob("*/SKILL.md")):
        shutil.copytree(skill.parent, target / skill.parent.name)


def invoked(question: str, skills: dict[str, Skill]) -> Skill | None:
    """질문 맨 앞의 `/이름`이 Paperloom 스킬이면 그 스킬."""
    match = COMMAND.match(question)
    return skills.get(match.group(1)) if match else None


def _frontmatter(text: str) -> dict:
    head, _, _ = text.replace("\r\n", "\n").removeprefix("---\n").partition("\n---\n")
    return yaml.safe_load(head)
