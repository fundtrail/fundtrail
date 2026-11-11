"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useState, type FormEvent } from "react";
import { useAuth } from "@/lib/auth";

/**
 * Local development only (ruling 63): an emailed sign-in link through Supabase,
 * shown when the build offers it.
 */
function EmailSignIn({ send }: { send: (email: string) => Promise<void> }) {
  const id = useId();
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent" | "failed">("idle");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!email.trim() || state === "sending") return;
    setState("sending");
    try {
      await send(email.trim());
      setState("sent");
    } catch {
      setState("failed");
    }
  }

  return (
    <form className="ft-si__email" onSubmit={(e) => void submit(e)} aria-label="Sign in with an email link">
      <label htmlFor={id} className="ft-label">
        Or, for local development, email me a sign-in link
      </label>
      <input id={id} type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
      <button type="submit" className="ft-btn" aria-disabled={state === "sending"}>
        {state === "sending" ? "Sending…" : "Email me a link"}
      </button>
      {state === "sent" && (
        <p className="ft-caption" role="status">
          Check your email for the sign-in link.
        </p>
      )}
      {state === "failed" && (
        <p className="ft-error" role="alert">
          The link wasn&apos;t sent. Try again.
        </p>
      )}
    </form>
  );
}

/** The only page a signed-out user sees: the wordmark, one line, one button. */
export default function SignIn() {
  const auth = useAuth();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (auth.state.status === "signed_in") router.replace("/");
  }, [auth.state.status, router]);

  async function signIn() {
    if (busy) return;
    setBusy(true);
    setFailed(false);
    try {
      await auth.signIn();
    } catch {
      setFailed(true);
      setBusy(false);
    }
  }

  return (
    <div className="ft-si">
      <div className="ft-si__card">
        <div className="ft-wordmark">FundTrail</div>
        <p>A running evidence file for every research grant, so the review is done before closeout.</p>
        {failed && (
          <p className="ft-error" role="alert">
            Sign-in didn&apos;t finish. Try again.
          </p>
        )}
        <button
          type="button"
          className={`ft-btn ft-btn--main ft-si__btn${busy ? " is-busy" : ""}`}
          aria-disabled={busy}
          onClick={() => void signIn()}
        >
          {busy ? "Signing in…" : "Continue with Google"}
        </button>
        {auth.signInWithEmail && <EmailSignIn send={auth.signInWithEmail} />}
        {auth.fake && (
          <p className="ft-caption">Fake sign-in: no Supabase project is configured, so this signs in a synthetic demo user.</p>
        )}
      </div>
    </div>
  );
}
