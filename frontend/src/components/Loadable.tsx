"use client";

import type { ReactNode } from "react";
import { describeError } from "@/lib/api/errors";

/**
 * Loading and error states for one piece of server data. The error says what
 * went wrong: not found (or not yours), a server problem, or a connection
 * problem. An expired session never shows here: it sends the user back to
 * sign-in (see providers.tsx).
 */
export function Loadable<T>({
  result,
  children,
}: {
  result: { data?: T; error?: unknown; isLoading: boolean };
  children: (data: T) => ReactNode;
}) {
  if (result.error) {
    return (
      <p className="ft-error" role="alert">
        {describeError(result.error).message}
      </p>
    );
  }
  if (result.data === undefined) return <p className="ft-empty">Loading…</p>;
  return <>{children(result.data)}</>;
}
