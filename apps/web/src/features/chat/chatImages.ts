/**
 * 대화 질문에 붙이는 이미지 (2026-11-10 사용자 요청). 붙여 넣기·끌어 놓기·첨부 단추로 받은 그림을 긴 변 MAX_SIDE px 이하로
 * 흰 바탕에 다시 그려 PNG로 보낸다(PNG가 너무 크면 JPEG). 브리지가 질문과 함께 Claude에 보내고 답과 함께 Paperloom에 저장한다
 * (backend/src/paperloom/answers/models.py ChatImage: PNG·JPEG, base64 5,000,000자까지, 한 질문에 넷까지).
 */

export const MAX_CHAT_IMAGES = 4;
/** 모델이 줄이지 않고 보는 긴 변 */
export const MAX_SIDE = 1568;
const MAX_BASE64_CHARS = 5_000_000;
const JPEG_QUALITY = 0.9;

export type ChatImage = Readonly<{ media_type: "image/png" | "image/jpeg"; data: string }>;

/** 입력칸에 붙인 이미지: 보낼 것과 미리 보기 주소(data: URL) */
export type AttachedImage = ChatImage & Readonly<{ id: string; url: string }>;

/** 긴 변이 max를 넘으면 비율을 지켜 줄인 크기 */
export function fitSize(width: number, height: number, max = MAX_SIDE): Readonly<{ width: number; height: number }> {
  const scale = Math.min(1, max / Math.max(width, height));
  return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)) };
}

/** 붙여 넣기·끌어 놓기·파일 고르기에서 이미지 파일만 */
export function imageFiles(files: FileList | null | undefined): File[] {
  return Array.from(files ?? []).filter((file) => file.type.startsWith("image/"));
}

let made = 0;

/** 그림 파일을 보낼 이미지로 다시 그린다. 읽지 못하는 그림(손상·브라우저가 모르는 형식)이면 거부한다. */
export async function prepareImage(file: Blob): Promise<AttachedImage> {
  const bitmap = await createImageBitmap(file);
  const { width, height } = fitSize(bitmap.width, bitmap.height);
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("canvas 2d를 쓸 수 없습니다.");
  context.fillStyle = "#fff"; // 투명한 곳: JPEG는 검게 칠하고, Claude는 흰 바탕으로 보는 게 원문에 가깝다
  context.fillRect(0, 0, width, height);
  context.drawImage(bitmap, 0, 0, width, height);
  bitmap.close();
  let url = canvas.toDataURL("image/png");
  let mediaType: ChatImage["media_type"] = "image/png";
  if (base64Of(url).length > MAX_BASE64_CHARS) {
    // 사진처럼 PNG로 큰 그림
    url = canvas.toDataURL("image/jpeg", JPEG_QUALITY);
    mediaType = "image/jpeg";
  }
  made += 1;
  return { id: `image-${made}`, media_type: mediaType, data: base64Of(url), url };
}

function base64Of(dataUrl: string): string {
  return dataUrl.slice(dataUrl.indexOf(",") + 1);
}
