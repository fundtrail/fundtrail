"use client";

import type { WriteState } from "@/lib/useWrite";
export { useWrite, type WriteState } from "@/lib/useWrite";

export function WriteProblems({ state }: { state: WriteState }) {
  if (state.status !== "failed") return null;
  return (
    <ul className="ft-error" role="alert">
      {state.problems.map((p, i) => (
        <li key={i}>{p}</li>
      ))}
    </ul>
  );
}
