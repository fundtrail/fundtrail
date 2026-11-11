import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import SignIn from "@/app/sign-in/page";
import { ApiProvider, usePings, useWorkspaces, type ApiClient } from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { signedInWith, StaticAuthProvider, type Auth } from "@/lib/auth";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }) }));

const user = { id: "u1", email: "accountant@university.example", name: null };

function auth(extra: Partial<Auth> = {}): Auth {
  return {
    state: { status: "signed_out" },
    fake: false,
    signIn: async () => {},
    signOut: async () => {},
    getAccessToken: async () => "t",
    ...extra,
  };
}

describe("the sign-in page", () => {
  it("offers only Google unless the build offers email sign-in", () => {
    render(
      <StaticAuthProvider value={auth()}>
        <SignIn />
      </StaticAuthProvider>,
    );
    expect(screen.getByRole("button", { name: "Continue with Google" })).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Sign in with an email link" })).toBeNull();
  });

  it("sends an email sign-in link when the build offers it (ruling 63)", async () => {
    const signInWithEmail = vi.fn(async () => {});
    render(
      <StaticAuthProvider value={auth({ signInWithEmail })}>
        <SignIn />
      </StaticAuthProvider>,
    );
    fireEvent.change(screen.getByLabelText(/email me a sign-in link/i), { target: { value: " accountant@university.example " } });
    fireEvent.click(screen.getByRole("button", { name: "Email me a link" }));
    await screen.findByText("Check your email for the sign-in link.");
    expect(signInWithEmail).toHaveBeenCalledWith("accountant@university.example");
  });
});

describe("signedInWith", () => {
  it("names how the user signed in, or just says signed in", () => {
    expect(signedInWith({ ...user, method: "google" })).toBe("Signed in with Google");
    expect(signedInWith({ ...user, method: "email" })).toBe("Signed in with an email link");
    expect(signedInWith({ ...user, method: null })).toBe("Signed in");
    expect(signedInWith(user)).toBe("Signed in");
  });
});

describe("usePings", () => {
  it("refetches what's on screen when the backend pings the channel, and stops listening on unmount", async () => {
    const client: ApiClient = createFakeApiClient();
    const list = vi.spyOn(client, "listWorkspaces");
    let ping: () => void = () => {};
    const stop = vi.fn();
    const listen = vi.fn((_topic: string, onPing: () => void) => {
      ping = onPing;
      return stop;
    });
    function Screen() {
      usePings("workspace:ws-sample");
      const { data } = useWorkspaces();
      return <p>{data ? data.length : "…"}</p>;
    }
    function Wrapper({ children }: { children: ReactNode }) {
      return (
        <StaticAuthProvider value={auth({ state: { status: "signed_in", user }, listen })}>
          <ApiProvider client={client}>{children}</ApiProvider>
        </StaticAuthProvider>
      );
    }
    const { unmount } = render(<Screen />, { wrapper: Wrapper });
    await waitFor(() => expect(list).toHaveBeenCalledTimes(1));
    expect(listen).toHaveBeenCalledWith("workspace:ws-sample", expect.any(Function));
    act(() => ping());
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
    unmount();
    expect(stop).toHaveBeenCalled();
  });
});
