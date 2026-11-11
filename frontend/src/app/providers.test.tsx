import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Providers } from "./providers";

describe("Providers", () => {
  it("fails loudly when a real setting is missing: an error screen names it and nothing else renders", () => {
    render(
      <Providers config={{ mode: "error", missing: ["NEXT_PUBLIC_API_URL", "NEXT_PUBLIC_SUPABASE_ANON_KEY"] }}>
        <p>the app</p>
      </Providers>,
    );
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("NEXT_PUBLIC_API_URL");
    expect(alert).toHaveTextContent("NEXT_PUBLIC_SUPABASE_ANON_KEY");
    expect(screen.queryByText("the app")).toBeNull();
    expect(screen.queryByText(/Fake mode/)).toBeNull();
  });

  it("labels every page as fake data in fake mode", () => {
    render(
      <Providers config={{ mode: "fake" }}>
        <p>the app</p>
      </Providers>,
    );
    expect(screen.getByRole("note")).toHaveTextContent("Fake mode: synthetic data");
    expect(screen.getByText("the app")).toBeInTheDocument();
  });

  it("shows no fake label in real mode", () => {
    render(
      <Providers
        config={{ mode: "real", apiUrl: "https://api.example", supabaseUrl: "https://project.supabase.example", supabaseAnonKey: "k", devEmailSignIn: false }}
      >
        <p>the app</p>
      </Providers>,
    );
    expect(screen.queryByText(/Fake mode/)).toBeNull();
    expect(screen.getByText("the app")).toBeInTheDocument();
  });
});
