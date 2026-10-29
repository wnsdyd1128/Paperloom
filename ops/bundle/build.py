"""Windows용 Paperloom 압축본을 만든다. Python·의존성·웹·모델을 모두 넣어 사용자는 Claude Code만 준비하면 된다.

실행(저장소 루트, 개발 환경은 README의 개발 절. 웹을 먼저 빌드한다: apps/web에서 npm ci, npm run build):
    backend\\.venv\\Scripts\\python.exe ops\\bundle\\build.py
결과는 dist/Paperloom-windows-x64.zip(안에 Paperloom 폴더)이고, 푼 폴더가 dist/Paperloom에 남는다. CI(.github/workflows/ci.yml)가
Windows 러너에서 만들어 ops/bundle/smoke.py로 시험하고, 릴리스(release.yml)가 GitHub Release에 붙인다.

- Python: Python 재단이 nuget.org에 올리는 64비트 Windows Python(python 패키지). 판과 sha256을 고정한다. C 헤더·링크 라이브러리·
  pip는 뺀다(실행에 쓰지 않는다).
- 의존성: requirements.lock(Docker 이미지와 같은 잠금)을 --require-hashes로, Windows용 wheel만 받아 넣는다.
- MSVC 런타임: onnxruntime은 msvcp140.dll·msvcp140_1.dll을 쓰는데 Python에는 vcruntime140*.dll만 있다. VC++ 재배포 패키지를
  깔지 않은 PC에서도 돌도록 Visual Studio의 재배포 폴더(Microsoft.VC14x.CRT)에서 python.exe 옆에 복사한다(앱 폴더 배포).
- python313._pth: 이 Python이 Lib·DLLs·site-packages만 보게 한다. 이 파일이 있으면 Python은 격리 모드로 돌아 사용자 PC의
  PYTHONPATH 같은 환경변수와 사용자 site-packages를 보지 않는다. 본문 추출 하위 프로세스(sys.executable)도 같다.
- 웹·모델: ops/config/bundle.yaml이 가리키는 자리에 넣는다. 모델은 코드가 고정한 주소·sha256(documents.layout_model·ocr_model)으로 받는다.
- 받은 파일은 dist/cache에 두고 다음 빌드에 다시 쓴다.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from paperloom import __version__
from paperloom.bootstrap.config import load_settings
from paperloom.documents import layout_model, ocr_model
from paperloom.infrastructure.onnx_models import download

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"

PYTHON_VERSION = "3.13.17"  # requirements*.lock을 만든 Python과 같은 3.13 (tests/contract/test_bundle.py)
PYTHON_URL = f"https://api.nuget.org/v3-flatcontainer/python/{PYTHON_VERSION}/python.{PYTHON_VERSION}.nupkg"
PYTHON_SHA256 = "dce409744b088f94c6e37ba41f8100c384c27e029e843237364c602d30d475e5"  # nuget.org 카탈로그의 SHA-512와 맞춰 봤다(2026-10-29)
PYTHON_MINOR = ".".join(PYTHON_VERSION.split(".")[:2])
PYTHON_TAG = PYTHON_MINOR.replace(".", "")
SKIPPED = ("include/", "libs/", "Lib/site-packages/")  # nupkg의 tools/ 아래에서 넣지 않는 것. site-packages는 여기서 채운다
MSVC_RUNTIME = ("msvcp140.dll", "msvcp140_1.dll")
WINDOWS_WHEELS = [
    "--platform", "win_amd64", "--python-version", PYTHON_MINOR, "--implementation", "cp", "--abi", f"cp{PYTHON_TAG}",
    "--only-binary=:all:",
]
ARCHIVE = "Paperloom-windows-x64.zip"  # README의 내려받기 주소(releases/latest/download/…)가 판마다 같도록 판을 넣지 않는다

# cmd는 배치 파일을 OEM 코드 페이지로 읽고 줄 끝이 LF뿐이면 잘못 읽을 수 있어 ASCII·CRLF로 쓴다. 실패하면 창을 닫기 전에 멈춘다
LAUNCHER = "\r\n".join([
    "@echo off",
    "rem Starts Paperloom (server and Claude Code bridge) and opens it in the browser. Close this window to stop it.",
    "rem Your library is kept outside this folder, in .paperloom\\data under your user folder.",
    "title Paperloom",
    '"%~dp0python\\python.exe" -m paperloom.launcher --config "%~dp0config\\paperloom.yaml"',
    "if errorlevel 1 pause",
    "",
])

NOTICES = """Paperloom {version} Windows 압축본에 함께 든 것과 그 라이선스

- Paperloom: MIT License (LICENSE.txt)
- Python {python} (python 폴더): Python Software Foundation License (python\\LICENSE.txt)
- Microsoft Visual C++ 런타임 (python 폴더의 vcruntime140.dll·vcruntime140_1.dll·msvcp140.dll·msvcp140_1.dll):
  Microsoft Visual Studio 사용 조건의 재배포 가능 코드
- Python 패키지 (python\\Lib\\site-packages): 패키지마다 *.dist-info 폴더에 라이선스가 있습니다
- PP-DocLayout_plus-L, PP-OCRv6_small_rec (models 폴더, PaddlePaddle): Apache License 2.0
  https://huggingface.co/PaddlePaddle/PP-DocLayout_plus-L_onnx
  https://huggingface.co/PaddlePaddle/PP-OCRv6_small_rec_onnx
- Wanted Sans 글꼴 (web 폴더): SIL Open Font License 1.1 (licenses\\Wanted-Sans-OFL.txt)
- PDF.js (web 폴더): Apache License 2.0
"""


def main() -> None:
    parser = argparse.ArgumentParser(prog="python ops/bundle/build.py", description="Windows용 Paperloom 압축본을 만든다")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "dist", help="결과 폴더 (기본 dist)")
    parser.add_argument("--vc-runtime", type=Path, help="msvcp140.dll·msvcp140_1.dll이 든 폴더 (기본: Visual Studio의 재배포 폴더)")
    args = parser.parse_args()
    if sys.version_info[:2] != tuple(map(int, PYTHON_MINOR.split("."))):
        raise SystemExit(f"Python {PYTHON_MINOR}로 실행하세요(넣는 패키지의 .pyc를 이 Python이 만든다).")
    web = REPO_ROOT / "apps" / "web" / "dist"
    if not (web / "index.html").is_file():
        raise SystemExit("웹을 먼저 빌드하세요: apps/web에서 npm ci, npm run build")
    runtime = args.vc_runtime or visual_studio_runtime()
    if missing := [name for name in MSVC_RUNTIME if not (runtime / name).is_file()]:
        raise SystemExit(f"{runtime}에 {', '.join(missing)}이 없습니다.")
    out = args.out.resolve()
    cache, root = out / "cache", out / "Paperloom"
    if root.exists():
        shutil.rmtree(root)

    python = root / "python"
    nupkg = cache / f"python.{PYTHON_VERSION}.nupkg"
    download(PYTHON_URL, PYTHON_SHA256, nupkg, f"Python {PYTHON_VERSION}")
    unpack_python(nupkg, python)
    for name in MSVC_RUNTIME:
        shutil.copy2(runtime / name, python / name)
    (python / f"python{PYTHON_TAG}._pth").write_text("Lib\nDLLs\nLib\\site-packages\nimport site\n", encoding="utf-8")
    install_packages(python / "Lib" / "site-packages")

    config = root / "config" / "paperloom.yaml"
    config.parent.mkdir()
    shutil.copy2(REPO_ROOT / "ops" / "config" / "bundle.yaml", config)
    settings = load_settings(config)
    shutil.copytree(web, settings.app.web_dist_dir)
    models = [
        (layout_model.MODEL_URL, layout_model.MODEL_SHA256, settings.layout.model_path),
        (ocr_model.MODEL_URL, ocr_model.MODEL_SHA256, settings.ocr.model_path),
        (ocr_model.DICTIONARY_URL, ocr_model.DICTIONARY_SHA256, settings.ocr.model_path.with_name("inference.yml")),
    ]
    for url, checksum, path in models:
        relative = path.relative_to(root)  # 설정이 압축본 밖을 가리키면 여기서 멈춘다
        download(url, checksum, cache / relative, relative.as_posix())
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cache / relative, path)

    (root / "Paperloom.cmd").write_bytes(LAUNCHER.encode("ascii"))
    shutil.copy2(REPO_ROOT / "LICENSE", root / "LICENSE.txt")
    (root / "licenses").mkdir()
    shutil.copy2(REPO_ROOT / "apps" / "web" / "src" / "shared" / "theme" / "fonts" / "OFL.txt", root / "licenses" / "Wanted-Sans-OFL.txt")
    # 메모장이 예전 Windows에서도 UTF-8로 읽도록 BOM을 붙인다
    notices = NOTICES.format(version=__version__, python=PYTHON_VERSION).replace("\n", "\r\n")
    (root / "THIRD-PARTY.txt").write_text(notices, encoding="utf-8-sig", newline="")
    archive(root, out / ARCHIVE)
    print(f"만들었습니다: {out / ARCHIVE} ({(out / ARCHIVE).stat().st_size / 1e6:.0f}MB)")


def visual_studio_runtime() -> Path:
    """Visual Studio 재배포 폴더의 64비트 MSVC 런타임(VC/Redist/MSVC/<판>/x64/Microsoft.VC14x.CRT). GitHub의 Windows 러너에 있다."""
    vswhere = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Microsoft Visual Studio", "Installer", "vswhere.exe")
    if not vswhere.is_file():
        raise SystemExit("Visual Studio를 찾지 못했습니다. --vc-runtime으로 msvcp140.dll·msvcp140_1.dll이 든 폴더를 알려 주세요.")
    command = [str(vswhere), "-latest", "-products", "*", "-property", "installationPath"]
    installed = Path(subprocess.run(command, capture_output=True, text=True, check=True).stdout.strip())
    folders = [
        folder
        for folder in installed.glob("VC/Redist/MSVC/*/x64/Microsoft.VC14*.CRT")
        if re.fullmatch(r"\d+(\.\d+)*", folder.parents[1].name)  # 판 폴더(14.44.35112)만. v143 같은 별칭 폴더는 뺀다
    ]
    if not folders:
        raise SystemExit(f"{installed}에 MSVC 재배포 폴더가 없습니다. --vc-runtime으로 알려 주세요.")
    return max(folders, key=lambda folder: tuple(int(part) for part in folder.parents[1].name.split(".")))


def unpack_python(nupkg: Path, target: Path) -> None:
    """nupkg(zip)의 tools/ 아래를 target에 푼다. SKIPPED는 뺀다."""
    with zipfile.ZipFile(nupkg) as package:
        for item in package.infolist():
            name = PurePosixPath(item.filename)
            if item.is_dir() or name.parts[0] != "tools":
                continue
            relative = PurePosixPath(*name.parts[1:])
            if relative.as_posix().startswith(SKIPPED):
                continue
            destination = target.joinpath(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with package.open(item) as source, destination.open("wb") as file:
                shutil.copyfileobj(source, file)


def install_packages(site: Path) -> None:
    """requirements.lock의 Windows용 wheel과 paperloom을 site에 넣는다."""
    pip = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-warn-script-location", "--target", str(site)]
    subprocess.run([*pip, *WINDOWS_WHEELS, "--require-hashes", "--no-deps", "-r", str(BACKEND / "requirements.lock")], check=True)
    with tempfile.TemporaryDirectory() as work:
        # 저장소의 backend에 빌드 찌꺼기(build·egg-info)를 남기지 않도록 복사본에서 설치한다
        source = Path(work) / "backend"
        shutil.copytree(BACKEND, source, ignore=shutil.ignore_patterns(".venv", "build", "*.egg-info", "__pycache__"))
        subprocess.run([*pip, "--no-deps", str(source)], check=True)
    for scripts in ("bin", "Scripts"):  # --target이 만든, 빌드한 PC의 Python을 가리키는 실행 스크립트
        shutil.rmtree(site / scripts, ignore_errors=True)


def archive(root: Path, target: Path) -> None:
    """root 폴더를 그 이름의 폴더째 zip으로 묶는다."""
    target.unlink(missing_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                bundle.write(path, PurePosixPath(root.name, *path.relative_to(root).parts).as_posix())


if __name__ == "__main__":
    main()
