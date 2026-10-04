/** 시각 표시. 저장된 시각은 UTC ISO 문자열이고, 화면은 이 PC의 시간대로 보인다. */

export function formatTime(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString("ko-KR") : "";
}

/** 목록에 쓰는 짧은 시각 (시안: 방금 · 2분 전 · 3시간 전 · 어제 · 5월 29일 · 2025. 12. 3.) */
export function relativeTime(iso: string, now: Date = new Date()): string {
  const then = new Date(iso);
  const minutes = Math.floor((now.getTime() - then.getTime()) / 60_000);
  if (minutes < 1) return "방금";
  if (minutes < 60) return `${minutes}분 전`;
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  if (then.getTime() >= startOfToday) return `${Math.floor(minutes / 60)}시간 전`;
  if (then.getTime() >= startOfToday - 86_400_000) return "어제";
  if (then.getFullYear() === now.getFullYear()) return `${then.getMonth() + 1}월 ${then.getDate()}일`;
  return `${then.getFullYear()}. ${then.getMonth() + 1}. ${then.getDate()}.`;
}
