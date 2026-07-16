import { ImageResponse } from "next/og";
import { readFile } from "node:fs/promises";
import { join } from "node:path";

/**
 * Direction 3b from the identity board: the 1280×640 card that does the work
 * when the repo lands on HN, Bluesky or r/ClaudeAI.
 *
 * Two deliberate departures from the board, both about not lying:
 *   - the board's subtitle promised "Claude Code, Codex & Copilot"; only the
 *     Claude Code adapter exists, so the copy says so.
 *   - the board carried a "★ 2.4k" badge. Inventing social proof for a repo is
 *     a fabricated metric, so it is gone.
 *
 * Rendered with Satori, which supports a subset of CSS: no CSS variables, no
 * class names, and every element in a multi-child container needs an explicit
 * display. Hence the inline styles and hardcoded hexes.
 */
export const alt =
  "nightaudit — an audit doesn't change the books. Read-only reviews while you're busy, one digest every morning.";
export const size = { width: 1280, height: 640 };
export const contentType = "image/png";

const ACCENT = "#8b9bff";
const MOON = "#ffd79a";

/**
 * One terminal row.
 *
 * Severity is a drawn dot rather than 🔴/✓: Satori has no glyph for those in
 * the default font and goes to the network to find one, which fails the build.
 * A div is a circle that always renders.
 */
function Line({
  stamp,
  text,
  color,
  stampColor = "#4a5680",
  dot,
}: {
  stamp: string;
  text: string;
  color: string;
  stampColor?: string;
  dot?: string;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "3px 0" }}>
      <span style={{ color: stampColor }}>{stamp}</span>
      {dot && (
        <div
          style={{
            width: 9,
            height: 9,
            borderRadius: 9999,
            background: dot,
            display: "flex",
          }}
        />
      )}
      <span style={{ color }}>{text}</span>
    </div>
  );
}

/** Satori has no font of its own — next/font is a browser concern and never
 *  reaches it. Without these the card silently renders in system sans, which
 *  is exactly the wrong look for the one asset whose job is to be the ad. */
async function fonts() {
  const dir = join(process.cwd(), "assets", "fonts");
  const [grotesk, mono, monoBold] = await Promise.all([
    readFile(join(dir, "space-grotesk-600.ttf")),
    readFile(join(dir, "jetbrains-mono-400.ttf")),
    readFile(join(dir, "jetbrains-mono-700.ttf")),
  ]);
  return [
    { name: "Space Grotesk", data: grotesk, weight: 600 as const, style: "normal" as const },
    { name: "JetBrains Mono", data: mono, weight: 400 as const, style: "normal" as const },
    { name: "JetBrains Mono", data: monoBold, weight: 700 as const, style: "normal" as const },
  ];
}

const STARS = [
  "radial-gradient(2px 2px at 12% 22%, rgba(255,255,255,.5), transparent)",
  "radial-gradient(2px 2px at 82% 18%, rgba(255,215,154,.6), transparent)",
  "radial-gradient(2px 2px at 60% 70%, rgba(139,155,255,.5), transparent)",
  "radial-gradient(1.5px 1.5px at 30% 82%, rgba(255,255,255,.35), transparent)",
  "radial-gradient(2px 2px at 92% 55%, rgba(160,200,255,.4), transparent)",
  "radial-gradient(120% 100% at 78% 12%, #141d3d 0%, #0a0f20 60%)",
].join(", ");

export default async function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          gap: 56,
          padding: "0 88px",
          backgroundColor: "#0a0f20",
          backgroundImage: STARS,
          fontFamily: "Space Grotesk",
        }}
      >
        {/* left: brand + promise */}
        <div style={{ display: "flex", flexDirection: "column", flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 18, marginBottom: 34 }}>
            <div
              style={{
                position: "relative",
                display: "flex",
                width: 64,
                height: 64,
                borderRadius: 18,
                background: "#131b38",
                alignItems: "center",
                justifyContent: "center",
                boxShadow: `0 0 40px -8px ${ACCENT}`,
              }}
            >
              <div
                style={{
                  position: "absolute",
                  top: 12,
                  right: 13,
                  width: 17,
                  height: 17,
                  borderRadius: 9999,
                  boxShadow: `inset -5px -1px 0 0 ${MOON}`,
                }}
              />
              <div
                style={{
                  fontSize: 22,
                  fontWeight: 700,
                  color: ACCENT,
                  marginTop: 12,
                  fontFamily: "JetBrains Mono",
                }}
              >
                &gt;_
              </div>
            </div>
            <div
              style={{
                fontSize: 40,
                fontWeight: 600,
                letterSpacing: "-0.02em",
                color: "#eef1ff",
                fontFamily: "JetBrains Mono",
              }}
            >
              nightaudit
            </div>
          </div>

          <div
            style={{
              fontSize: 52,
              fontWeight: 600,
              lineHeight: 1.08,
              letterSpacing: "-0.02em",
              color: "#f4f6fc",
              marginBottom: 22,
              display: "flex",
              flexDirection: "column",
            }}
          >
            <span>An audit doesn&apos;t</span>
            <span>change the books.</span>
          </div>

          <div
            style={{
              fontSize: 21,
              lineHeight: 1.5,
              color: "#93a1c4",
              marginBottom: 34,
              maxWidth: 520,
            }}
          >
            Put your idle Claude Code subscription to work — read-only reviews
            while you&apos;re busy, one digest every morning.
          </div>

          {/* Stacked, not side by side. Beside each other these two fit only
              at one specific package-name length — an earlier rename silently
              clipped the button mid-word. A column survives any name.
              flexShrink:0 so the button is never squeezed into its own text. */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "flex-start",
              gap: 16,
            }}
          >
            <div
              style={{
                flexShrink: 0,
                fontSize: 20,
                fontWeight: 700,
                color: "#06090f",
                background: ACCENT,
                borderRadius: 11,
                padding: "14px 24px",
                fontFamily: "JetBrains Mono",
                whiteSpace: "nowrap",
              }}
            >
              pipx install nightaudit
            </div>
            <div
              style={{
                fontSize: 16,
                color: "#8593b8",
                fontFamily: "JetBrains Mono",
                whiteSpace: "nowrap",
              }}
            >
              github.com/kishormorol/nightaudit
            </div>
          </div>
        </div>

        {/* right: the run */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            width: 440,
            borderRadius: 16,
            border: "1px solid #263050",
            background: "#080c1a",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "14px 18px",
              borderBottom: "1px solid #131a30",
              background: "#0d1326",
            }}
          >
            <div style={{ display: "flex", gap: 8 }}>
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  style={{ width: 12, height: 12, borderRadius: 9999, background: "#26304d" }}
                />
              ))}
            </div>
            <div style={{ fontSize: 15, color: "#5f6c80", fontFamily: "JetBrains Mono" }}>
              nightaudit run
            </div>
          </div>

          <div
            style={{
              display: "flex",
              flexDirection: "column",
              padding: 22,
              fontSize: 16,
              fontFamily: "JetBrains Mono",
            }}
          >
            <Line stamp="$" stampColor={ACCENT} color="#5f6c80" text="nightaudit run" />
            <Line stamp="[09:14]" color="#8593b8" text="→ gradagent · security_audit" />
            <Line stamp="[09:14]" color="#ff8b84" text="HIGH auth.py:142" dot="#ff5b52" />
            <Line stamp="[09:16]" color="#8593b8" text="→ payments-web · deps_audit" />
            <Line stamp="[09:16]" color="#6fdd8b" text="digest queued · 06:00" dot="#6fdd8b" />
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 14,
                marginTop: 16,
                paddingTop: 14,
                borderTop: "1px solid #131a30",
                fontSize: 14,
              }}
            >
              <span style={{ color: "#6472a0" }}>0 files touched</span>
              <span style={{ color: "#263050" }}>·</span>
              <span style={{ color: "#6fdd8b" }}>read-only</span>
            </div>
          </div>
        </div>
      </div>
    ),
    { ...size, fonts: await fonts() },
  );
}
