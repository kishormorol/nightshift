import { ImageResponse } from "next/og";

/**
 * The favicon, generated rather than committed as a binary.
 *
 * The board's own test was whether the mark survives 16px. At this size the
 * `>_` glyph turns to mush, so the icon keeps only the crescent on the tile —
 * the one shape that still reads.
 */
export const size = { width: 32, height: 32 };
export const contentType = "image/png";

export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          background: "#131b38",
          borderRadius: 8,
          position: "relative",
        }}
      >
        <div
          style={{
            position: "absolute",
            top: 6,
            right: 6,
            width: 16,
            height: 16,
            borderRadius: 9999,
            boxShadow: "inset -4px -1px 0 0 #ffd79a",
          }}
        />
      </div>
    ),
    { ...size },
  );
}
