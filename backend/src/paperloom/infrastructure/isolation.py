"""신뢰할 수 없는 PDF를 다루는 하위 프로세스의 자원 제한 (IMPL §5.1).

POSIX(컨테이너)에서는 메모리·CPU 제한을 건다. Windows에는 해당 기능이 없어 호출하는 쪽의 시간 제한만 적용된다.
"""

_MEMORY_LIMIT_BYTES = 1 << 30
_CPU_LIMIT_SECONDS = 30


def limit_resources() -> None:
    """하위 프로세스 시작 직후 부른다."""
    try:
        import resource
    except ImportError:  # Windows
        return
    resource.setrlimit(resource.RLIMIT_AS, (_MEMORY_LIMIT_BYTES, _MEMORY_LIMIT_BYTES))
    resource.setrlimit(resource.RLIMIT_CPU, (_CPU_LIMIT_SECONDS, _CPU_LIMIT_SECONDS))
