"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useState, type FormEvent } from "react";
import { TrailMark } from "@/components/TrailMark";
import { takeSessionExpired, useAuth } from "@/lib/auth";
import styles from "./signin.module.css";
import { TrailArt } from "./TrailArt";

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
    <form className={styles.email} onSubmit={(e) => void submit(e)} aria-label="Sign in with an email link">
      <label htmlFor={id} className="ft-label">
        Or, for local development, email me a sign-in link
      </label>
      <div className={styles.emailRow}>
        <input id={id} type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        <button type="submit" className={`ft-btn${state === "sending" ? " is-busy" : ""}`} aria-disabled={state === "sending"}>
          {state === "sending" ? "Sending…" : "Email me a link"}
        </button>
      </div>
      {state === "sent" && (
        <p className={styles.emailNote} role="status">
          Check your email for the sign-in link.
        </p>
      )}
      {state === "failed" && (
        <p className={`ft-error ${styles.emailError}`} role="alert">
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
  // Whether the user lands here because the server refused the session, read once.
  const [expired, setExpired] = useState(false);
  useEffect(() => {
    // Storage is read after mount: it isn't there while rendering on the server.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (takeSessionExpired()) setExpired(true);
  }, []);

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
    <div className={styles.page}>
      <div className={styles.brand}>
        <h1 className={styles.wordmark}>
          <TrailMark className={styles.glyph} width={34} />
          FundTrail
        </h1>
        <p className={styles.line}>A running evidence file for every research grant, so the review is done before closeout.</p>
        <TrailArt className={styles.art} classes={styles} />
      </div>
      <main className={styles.paper}>
        <div className={styles.panel}>
          <h2 className={styles.title}>Sign in</h2>
          {expired && !failed && (
            <p className={styles.note} role="status">
              Your session has expired. Sign in again.
            </p>
          )}
          {failed && (
            <p className={styles.alert} role="alert">
              Sign-in didn&apos;t finish. Try again.
            </p>
          )}
          <button
            type="button"
            className={`ft-btn ft-btn--main ${styles.signIn}${busy ? " is-busy" : ""}`}
            aria-disabled={busy}
            onClick={() => void signIn()}
          >
            {busy ? "Signing in…" : "Continue with Google"}
          </button>
          {auth.signInWithEmail && <EmailSignIn send={auth.signInWithEmail} />}
          {auth.fake && (
            <p className={`ft-caption ${styles.fine}`}>
              Fake sign-in: no Supabase project is configured, so this signs in a synthetic demo user.
            </p>
          )}
        </div>
      </main>
    </div>
  );
}
