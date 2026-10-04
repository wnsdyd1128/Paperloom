/** REST 응답 처리 공용 도구. 오류는 IMPL §8의 봉투(code, message, request_id, retryable, details)로 온다. */

export type ApiErrorBody = Readonly<{
  code: string;
  message: string;
  request_id: string;
  retryable: boolean;
  details?: Readonly<Record<string, unknown>>;
}>;

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: ApiErrorBody,
  ) {
    super(body.message);
  }
}

export async function parseJson<T>(response: Response): Promise<T> {
  const body: unknown = await response.json();
  if (!response.ok) throw new ApiError(response.status, body as ApiErrorBody);
  return body as T;
}

/** 본문이 없는 성공 응답(204 등)을 기다린다. 실패하면 오류 봉투로 ApiError를 던진다. */
export async function expectOk(response: Response): Promise<void> {
  if (!response.ok) throw new ApiError(response.status, (await response.json()) as ApiErrorBody);
}

export function jsonRequest(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

/**
 * 만들기 요청(POST). 재전송 방지 키(IMPL §8)를 붙이고, 응답을 받지 못한 네트워크 오류면 같은 키로 한 번 더 보낸다.
 * 서버는 같은 키의 요청을 한 번만 처리하고 처음 응답을 돌려준다.
 */
export async function postJson(url: string, body: unknown): Promise<Response> {
  const key = newIdempotencyKey();
  const send = () =>
    fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Idempotency-Key": key },
      body: JSON.stringify(body),
    });
  try {
    return await send();
  } catch (error) {
    if (!(error instanceof TypeError)) throw error; // fetch는 네트워크 오류를 TypeError로 알린다
    return await send();
  }
}

/** crypto.randomUUID는 보안 출처(https·localhost)에서만 있으므로 어디서나 되는 getRandomValues로 만든다. */
export function newIdempotencyKey(): string {
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) => byte.toString(16).padStart(2, "0")).join("");
}
