import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Loadable } from "./Loadable";

describe("Loadable", () => {
  const failed = { data: { n: 1 }, error: new TypeError("Failed to fetch"), isLoading: false };

  it("offers Try again on an error only when the screen asks, and it only calls the retry", () => {
    const onRetry = vi.fn();
    const { unmount } = render(<Loadable result={failed}>{(d) => <p>{d.n}</p>}</Loadable>);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
    unmount();
    render(
      <Loadable result={failed} onRetry={onRetry}>
        {(d) => <p>{d.n}</p>}
      </Loadable>,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
