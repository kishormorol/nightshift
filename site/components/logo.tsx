/**
 * The mark from the identity board: a glowing tile carrying a terminal prompt,
 * with a crescent moon clipped to its top-right corner.
 *
 * Everything scales off `size` so the same component serves the nav, the
 * footer and the og:image without a second implementation drifting away from
 * the first.
 */
export function Mark({ size = 30 }: { size?: number }) {
  return (
    <div
      className="relative flex flex-none items-center justify-center rounded-[0.3em] bg-navy-500"
      style={{
        width: size,
        height: size,
        borderRadius: size * 0.3,
        boxShadow: `0 0 ${size * 0.55}px -${size * 0.17}px rgba(139,155,255,.6)`,
      }}
      aria-hidden="true"
    >
      <div
        className="moon absolute"
        style={{
          top: size * 0.2,
          right: size * 0.2,
          width: size * 0.3,
          height: size * 0.3,
          fontSize: size * 0.3,
        }}
      />
      <span
        className="font-mono font-bold text-accent"
        style={{ fontSize: size * 0.4, marginTop: size * 0.2 }}
      >
        &gt;_
      </span>
    </div>
  );
}

export function Wordmark({ size = 30 }: { size?: number }) {
  return (
    <span className="flex items-center gap-[0.37em]">
      <Mark size={size} />
      <span
        className="font-mono font-semibold tracking-[-0.02em] text-fg"
        style={{ fontSize: size * 0.53 }}
      >
        nightaudit
      </span>
    </span>
  );
}
