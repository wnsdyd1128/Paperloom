/**
 * 키가 펼친 select 목록 안에서 눌렸는지. 고칠 수 있는 select(appearance: base-select, shared/theme/components.css)의
 * 목록은 운영체제 목록과 달리 키를 페이지에도 보내고, 열린 동안 포커스는 항목(option)에 있다. 창·모드를 끝내는 Esc는
 * 이때 건너뛰어 목록만 닫히게 한다(2026-11-13: 설정 창 목록에서 Esc를 누르면 설정 창까지 닫혔다).
 */
export function inSelectPicker(event: KeyboardEvent): boolean {
  return event.target instanceof HTMLOptionElement;
}
