/**
 * 화면 아이콘. 디자인 시스템이 정한 Lucide(https://lucide.dev, ISC) 모양을 시안에서 옮겼다. 의존성을 더하지 않으려고
 * 쓰는 것만 둔다. 아이콘은 장식이므로 화면 낭독기에서 숨기고, 단추 이름은 단추에 따로 붙인다.
 */

type Shape = string | Readonly<{ rect: readonly [number, number, number, number] }> | Readonly<{ circle: readonly [number, number, number] }>;

const ICONS = {
  list: ["M3 6h.01", "M3 12h.01", "M3 18h.01", "M8 6h13", "M8 12h13", "M8 18h13"],
  grid: [{ rect: [3, 3, 7, 7] }, { rect: [14, 3, 7, 7] }, { rect: [14, 14, 7, 7] }, { rect: [3, 14, 7, 7] }],
  filter: ["M22 3H2l8 9.46V19l4 2v-8.54L22 3z"],
  upload: ["M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4", "m17 8-5-5-5 5", "M12 3v12"],
  info: [{ circle: [12, 12, 10] }, "M12 16v-4", "M12 8h.01"],
  search: [{ circle: [11, 11, 8] }, "m21 21-4.3-4.3"],
  chevronDown: ["m6 9 6 6 6-6"],
  chevronUp: ["m18 15-6-6-6 6"],
  minus: ["M5 12h14"],
  plus: ["M5 12h14", "M12 5v14"],
  region: [
    "M5 3a2 2 0 0 0-2 2", "M19 3a2 2 0 0 1 2 2", "M21 19a2 2 0 0 1-2 2", "M5 21a2 2 0 0 1-2-2", "M9 3h1", "M9 21h1",
    "M14 3h1", "M14 21h1", "M3 9v1", "M21 9v1", "M3 14v1", "M21 14v1",
  ],
  languages: ["m5 8 6 6", "m4 14 6-6 2-3", "M2 5h12", "M7 2h1", "m22 22-5-10-5 10", "M14 18h6"],
  fileText: [
    "M14 2v4a2 2 0 0 0 2 2h4", "M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z", "M8 13h8", "M8 17h5",
  ],
  settings: [
    "M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z",
    { circle: [12, 12, 3] },
  ],
  share: ["M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8", "m16 6-4-4-4 4", "M12 2v13"],
  panel: [{ rect: [3, 3, 18, 18] }, "M15 3v18"],
  toSidebar: [{ rect: [3, 3, 18, 18] }, "M15 3v18", "m8 9 3 3-3 3"],
  chat: ["M14 9a2 2 0 0 1-2 2H6l-4 4V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2z", "M18 9h2a2 2 0 0 1 2 2v11l-4-4h-6a2 2 0 0 1-2-2v-1"],
  sparkles: [
    "M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z",
  ],
  highlighter: ["m9 11-6 6v3h9l3-3", "m22 12-4.6 4.6a2 2 0 0 1-2.8 0l-5.2-5.2a2 2 0 0 1 0-2.8L14 4"],
  note: ["M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"],
  notes: ["M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z", "M8 9h8"],
  ask: ["M7.9 20A9 9 0 1 0 4 16.1L2 22Z", "M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3", "M12 17h.01"],
  trash: ["M3 6h18", "M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6", "M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"],
  collapse: ["m14 10 7-7", "M20 10h-6V4", "m3 21 7-7", "M4 14h6v6"],
  expand: ["M15 3h6v6", "m21 3-7 7", "m3 21 7-7", "M9 21H3v-6"],
  copy: [{ rect: [8, 8, 14, 14] }, "M4 16V4h12"],
  x: ["M18 6 6 18", "m6 6 12 12"],
  history: ["M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8", "M3 3v5h5", "M12 7v5l4 2"],
  arrowUp: ["m5 12 7-7 7 7", "M12 19V5"],
  arrowLeft: ["m12 19-7-7 7-7", "M19 12H5"],
  check: ["M20 6 9 17l-5-5"],
  type: ["M4 7V4h16v3", "M9 20h6", "M12 4v16"],
  rotate: ["M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8", "M21 3v5h-5"],
  link: [
    "M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71",
    "M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71",
  ],
  pencil: ["M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"],
  // Lucide git-fork (갈래), square (중단)
  fork: [{ circle: [12, 18, 3] }, { circle: [6, 6, 3] }, { circle: [18, 6, 3] }, "M18 9v2c0 .6-.4 1-1 1H7c-.6 0-1-.4-1-1V9", "M12 12v3"],
  stop: [{ rect: [6, 6, 12, 12] }],
} satisfies Record<string, readonly Shape[]>;

export type IconName = keyof typeof ICONS;

export function Icon({ name, size = 16, className }: Readonly<{ name: IconName; size?: number; className?: string }>) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {(ICONS[name] as readonly Shape[]).map((shape, index) =>
        typeof shape === "string" ? (
          <path key={index} d={shape} />
        ) : "rect" in shape ? (
          <rect key={index} x={shape.rect[0]} y={shape.rect[1]} width={shape.rect[2]} height={shape.rect[3]} />
        ) : (
          <circle key={index} cx={shape.circle[0]} cy={shape.circle[1]} r={shape.circle[2]} />
        ),
      )}
    </svg>
  );
}
