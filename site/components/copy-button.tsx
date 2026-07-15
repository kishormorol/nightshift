"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Copies the quickstart. Confirms in place rather than via a toast — the
 * button is what you clicked, so the button is where the answer belongs.
 */
export function CopyButton({ text, label = "copy" }: { text: string; label?: string }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => () => clearTimeout(timer.current), []);

  async function copy() {
    try {
      // Absent over plain HTTP and in older browsers — never assume it's there.
      await navigator.clipboard.writeText(text);
      setState("copied");
    } catch {
      setState("failed");
    }
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setState("idle"), 1600);
  }

  return (
    <button
      type="button"
      onClick={copy}
      className="cursor-pointer rounded-lg border border-line-500 px-4 py-3 font-mono text-[13px] text-fg-muted transition-colors hover:border-line-400 hover:text-fg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
    >
      <span aria-hidden="true">
        {state === "copied" ? "copied ✓" : state === "failed" ? "copy failed" : label}
      </span>
      <span className="sr-only">
        {state === "copied"
          ? "Quickstart copied to clipboard"
          : state === "failed"
            ? "Copy failed — select the command manually"
            : "Copy the quickstart commands"}
      </span>
      <span aria-live="polite" className="sr-only">
        {state === "copied" ? "Copied" : state === "failed" ? "Copy failed" : ""}
      </span>
    </button>
  );
}
