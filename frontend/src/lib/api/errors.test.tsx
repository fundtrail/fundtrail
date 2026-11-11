import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import SignIn from "@/app/sign-in/page";
import { Loadable } from "@/components/Loadable";
import { markSessionExpired, StaticAuthProvider, type Auth } from "../auth";
import { ApiError, HttpApiClient } from "./client";
import { describeError } from "./errors";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }) }));

afterEach(() => vi.unstubAllGlobals());

describe("describeError", () => {
  it("says what went wrong", () => {
    expect(describeError(new ApiError(404, "Not Found")).kind).toBe("not_found");
    expect(describeError(new ApiError(403, null)).kind).toBe("not_found");
    expect(describeError(new ApiError(500, null)).kind).toBe("server");
    expect(describeError(new ApiError(503, null)).kind).toBe("server");
    expect(describeError(new ApiError(0, null)).kind).toBe("connection");
    expect(describeError(new TypeError("Failed to fetch")).kind).toBe("connection");
    expect(describeError(new ApiError(401, null)).kind).toBe("session");
    expect(describeError(new ApiError(422, ["The amount is missing."]))).toEqual({ kind: "rejected", message: "The amount is missing." });
  });
});

describe("HttpApiClient", () => {
  it("turns a failed connection into a status-0 ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));
    const error = await new HttpApiClient("https://api.example", async () => "t").listWorkspaces().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(0);
  });

  it("reports a refused session before throwing, and a missing one too", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "Invalid token" }), { status: 401 })));
    const onUnauthorized = vi.fn();
    await expect(new HttpApiClient("https://api.example", async () => "t", onUnauthorized).listWorkspaces()).rejects.toMatchObject({ status: 401 });
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
    await expect(new HttpApiClient("https://api.example", async () => null, onUnauthorized).listWorkspaces()).rejects.toMatchObject({ status: 401 });
    expect(onUnauthorized).toHaveBeenCalledTimes(2);
  });

  it("doesn't report a 404 as a session problem", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 404 })));
    const onUnauthorized = vi.fn();
    await expect(new HttpApiClient("https://api.example", async () => "t", onUnauthorized).getGrant("g")).rejects.toMatchObject({ status: 404 });
    expect(onUnauthorized).not.toHaveBeenCalled();
  });
});

describe("Loadable", () => {
  it("shows what went wrong instead of a generic message", () => {
    render(<Loadable result={{ error: new ApiError(404, null), isLoading: false }}>{() => null}</Loadable>);
    expect(screen.getByRole("alert")).toHaveTextContent("Not found, or not yours to see.");
  });
});

describe("the sign-in page after an expired session", () => {
  it("says the session expired, once", () => {
    const auth: Auth = { state: { status: "signed_out" }, fake: false, signIn: async () => {}, signOut: async () => {}, getAccessToken: async () => null };
    markSessionExpired();
    const { unmount } = render(
      <StaticAuthProvider value={auth}>
        <SignIn />
      </StaticAuthProvider>,
    );
    expect(screen.getByText("Your session has expired. Sign in again.")).toBeInTheDocument();
    unmount();
    render(
      <StaticAuthProvider value={auth}>
        <SignIn />
      </StaticAuthProvider>,
    );
    expect(screen.queryByText("Your session has expired. Sign in again.")).toBeNull();
  });
});
