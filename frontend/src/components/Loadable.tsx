"use client";

import type { ReactNode } from "react";
import { describeError } from "@/lib/api/errors";

/**
 * Loading and error states for one piece of server data. The error says what
 * went wrong: not found (or not yours), a server problem, or a connection
 * problem. An expired session never shows here: it sends the user back to
 * sign-in (see providers.tsx). With `onRetry`, the error offers Try again,
 * which loads the data again and sends nothing else: for a screen where a
 * decision was just saved and the refetch after it failed.
 */
export function Loadable<T>({
  result,
  children,
  onRetry,
}: {
  result: { data?: T; error?: unknown; isLoading: boolean };
  children: (data: T) => ReactNode;
  onRetry?: () => void;
}) {
  if (result.error) {
    return (
      <>
        <p className="ft-error" role="alert">
          {describeError(result.error).message}
        </p>
        {onRetry && (
          <p>
            <button type="button" className="ft-btn ft-btn--sm" disabled={result.isLoading} onClick={onRetry}>
              Try again
            </button>
          </p>
        )}
      </>
    );
  }
  if (result.data === undefined) return <p className="ft-empty">Loading…</p>;
  return <>{children(result.data)}</>;
}
