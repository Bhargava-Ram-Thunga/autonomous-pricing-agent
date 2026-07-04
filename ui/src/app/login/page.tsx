"use client";

import { useState } from "react";
import { Alert, Button, Separator, Spinner } from "@heroui/react";
import { ArrowRightIcon } from "lucide-react";

type GoogleAccountsId = {
  initialize: (cfg: {
    client_id: string | undefined;
    callback: (r: { credential: string }) => void;
  }) => void;
  prompt: () => void;
};

function GoogleIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24">
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
      <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
    </svg>
  );
}

/** A ticking price line, drawn once on mount — the one motif this screen is built around. */
function TickerMark() {
  return (
    <svg viewBox="0 0 64 64" className="size-8" fill="none">
      <path
        d="M6 40 L20 40 L26 22 L34 48 L40 30 L46 36 L58 12"
        stroke="#fbbf24"
        strokeWidth="4"
        strokeLinecap="round"
        strokeLinejoin="round"
        pathLength={1}
        className="login-mark"
      />
    </svg>
  );
}

export default function LoginPage() {
  const [loading, setLoading] = useState(false);
  const [demoLoading, setDemoLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCredentialResponse(response: { credential: string }) {
    setLoading(true);
    try {
      const res = await fetch("/api/auth/google", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ idToken: response.credential }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError((data as { error?: string }).error ?? "Authentication failed");
        return;
      }
      window.location.href = "/rooms";
    } catch {
      setError("Network error during sign-in");
    } finally {
      setLoading(false);
    }
  }

  function handleGoogleSignIn() {
    setLoading(true);
    setError(null);
    try {
      const g = (window as unknown as { google?: { accounts?: { id?: GoogleAccountsId } } }).google;
      const client = g?.accounts?.id;
      if (!client) {
        setError("Google sign-in not configured for this deployment.");
        setLoading(false);
        return;
      }
      client.prompt();
    } catch {
      setError("Sign-in failed");
      setLoading(false);
    }
  }

  async function handleDemoSignIn() {
    setDemoLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/demo", { method: "POST" });
      if (!res.ok) {
        setError("Could not start demo session");
        return;
      }
      window.location.href = "/rooms";
    } catch {
      setError("Network error starting demo session");
    } finally {
      setDemoLoading(false);
    }
  }

  return (
    <>
      <script
        src="https://accounts.google.com/gsi/client"
        onLoad={() => {
          const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
          if (!clientId) return;
          const g = (window as unknown as { google?: { accounts?: { id?: GoogleAccountsId } } }).google;
          g?.accounts?.id?.initialize({
            client_id: clientId,
            callback: handleCredentialResponse,
          });
        }}
        async
        defer
      />

      <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[#08090b] px-6 py-16">
        {/* atmosphere: faint grid + drifting amber glow + noise */}
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.07]"
          style={{
            backgroundImage:
              "linear-gradient(to right, #ffffff 1px, transparent 1px), linear-gradient(to bottom, #ffffff 1px, transparent 1px)",
            backgroundSize: "56px 56px",
          }}
        />
        <div
          className="login-glow pointer-events-none absolute -top-40 left-1/2 h-[36rem] w-[36rem] -translate-x-1/2 rounded-full opacity-25 blur-[110px]"
          style={{ background: "radial-gradient(circle, #fbbf24 0%, transparent 70%)" }}
        />
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.035] mix-blend-overlay"
          style={{
            backgroundImage:
              "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")",
          }}
        />

        {/* the drawn ticker line running across the whole scene */}
        <svg
          className="pointer-events-none absolute inset-x-0 top-[18%] h-40 w-full opacity-60"
          viewBox="0 0 1200 200"
          preserveAspectRatio="none"
          fill="none"
        >
          <path
            d="M0 140 L140 140 L200 60 L260 170 L340 40 L420 110 L480 80 L560 150 L640 30 L740 120 L820 70 L920 160 L1000 50 L1080 100 L1200 60"
            stroke="url(#tickerGradient)"
            strokeWidth="1.5"
            strokeDasharray="1400"
            className="login-ticker-path"
          />
          <defs>
            <linearGradient id="tickerGradient" x1="0" x2="1" y1="0" y2="0">
              <stop offset="0%" stopColor="#fbbf24" stopOpacity="0" />
              <stop offset="15%" stopColor="#fbbf24" stopOpacity="0.7" />
              <stop offset="85%" stopColor="#fbbf24" stopOpacity="0.7" />
              <stop offset="100%" stopColor="#fbbf24" stopOpacity="0" />
            </linearGradient>
          </defs>
        </svg>

        {/* card */}
        <div
          className="relative w-full max-w-[26rem] rounded-2xl border border-white/[0.08] bg-[#0d0e11]/90 p-10 shadow-[0_0_0_1px_rgba(251,191,36,0.06),0_40px_100px_-30px_rgba(0,0,0,0.9)] backdrop-blur-xl"
        >
          <div className="mb-9 flex flex-col items-center gap-4 text-center">
            <TickerMark />
            <div>
              <h1
                className="text-[2.1rem] leading-none font-medium tracking-tight text-white"
                style={{ fontFamily: "var(--font-display)" }}
              >
                Pricing Agent
              </h1>
              <p
                className="mt-3 text-[0.75rem] tracking-[0.14em] text-white/35 uppercase"
                style={{ fontFamily: "var(--font-mono)" }}
              >
                Autonomous · Always Watching
              </p>
            </div>
          </div>

          {error && (
            <Alert status="danger" className="mb-5">
              <Alert.Content>
                <Alert.Description>{error}</Alert.Description>
              </Alert.Content>
            </Alert>
          )}

          <div className="flex flex-col gap-3">
            <Button
              variant="primary"
              size="lg"
              fullWidth
              onPress={handleGoogleSignIn}
              isDisabled={loading || demoLoading}
              className="!bg-white !text-black hover:!bg-white/90"
            >
              <GoogleIcon />
              {loading ? (
                <>
                  <Spinner size="sm" /> Signing in…
                </>
              ) : (
                "Continue with Google"
              )}
            </Button>

            <div className="my-1 flex items-center gap-3">
              <Separator className="flex-1 opacity-20" />
              <span
                className="text-[0.65rem] tracking-[0.2em] text-white/30 uppercase"
                style={{ fontFamily: "var(--font-mono)" }}
              >
                or
              </span>
              <Separator className="flex-1 opacity-20" />
            </div>

            <button
              onClick={() => void handleDemoSignIn()}
              disabled={loading || demoLoading}
              className="group flex w-full items-center justify-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] py-3 text-sm text-white/60 transition-colors hover:bg-white/[0.06] hover:text-white/90 disabled:opacity-40"
            >
              {demoLoading ? (
                <>
                  <Spinner size="sm" /> Starting demo…
                </>
              ) : (
                <>
                  Explore without an account
                  <ArrowRightIcon className="size-3.5 -translate-x-0.5 opacity-0 transition-all group-hover:translate-x-0 group-hover:opacity-100" />
                </>
              )}
            </button>
          </div>

          <p
            className="mt-7 text-center text-[0.7rem] leading-relaxed text-white/25"
            style={{ fontFamily: "var(--font-mono)" }}
          >
            Demo mode skips Google auth
            <br />
            no real portal credentials touched
          </p>
        </div>
      </div>
    </>
  );
}
