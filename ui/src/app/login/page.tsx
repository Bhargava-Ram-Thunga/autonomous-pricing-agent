"use client";

import { useId, useState } from "react";
import { Alert, Button, Spinner } from "@heroui/react";
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
    <svg width="17" height="17" viewBox="0 0 24 24" aria-hidden="true">
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
      <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
    </svg>
  );
}

function TickerMark() {
  return (
    <svg viewBox="0 0 64 64" className="size-9 shrink-0" fill="none" aria-hidden="true">
      <path
        d="M6 40 L20 40 L26 22 L34 48 L40 30 L46 36 L58 12"
        stroke="#fbbf24"
        strokeWidth="4.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        pathLength={1}
        className="login-mark"
      />
    </svg>
  );
}

/** Ambient price-graph backdrop: two staggered lines, a soft drift, and a few pulsing data points. */
function GraphBackdrop() {
  return (
    <svg
      className="login-graph pointer-events-none absolute inset-x-[-5%] top-[10%] h-[26rem] w-[110%] opacity-40"
      viewBox="0 0 1200 400"
      preserveAspectRatio="none"
      fill="none"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="tickerGradientBack" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stopColor="#fbbf24" stopOpacity="0" />
          <stop offset="20%" stopColor="#fbbf24" stopOpacity="0.12" />
          <stop offset="80%" stopColor="#fbbf24" stopOpacity="0.12" />
          <stop offset="100%" stopColor="#fbbf24" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="tickerGradient" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stopColor="#fbbf24" stopOpacity="0" />
          <stop offset="15%" stopColor="#fbbf24" stopOpacity="0.5" />
          <stop offset="85%" stopColor="#fbbf24" stopOpacity="0.5" />
          <stop offset="100%" stopColor="#fbbf24" stopOpacity="0" />
        </linearGradient>
      </defs>

      <path
        d="M-40 260 L100 260 L170 190 L230 300 L320 150 L400 230 L470 190 L560 280 L650 130 L760 250 L850 170 L960 290 L1050 140 L1140 210 L1240 150"
        stroke="url(#tickerGradientBack)"
        strokeWidth="1.5"
      />
      <path
        d="M-40 200 L100 200 L170 90 L230 260 L320 40 L400 160 L470 110 L560 230 L650 20 L760 180 L850 90 L960 250 L1050 60 L1140 150 L1240 90"
        stroke="url(#tickerGradient)"
        strokeWidth="1.5"
        strokeDasharray="1600"
        className="login-ticker-path"
      />

      {[
        [320, 40],
        [650, 20],
        [1050, 60],
      ].map(([cx, cy], i) => (
        <circle
          key={i}
          cx={cx}
          cy={cy}
          r="4"
          fill="#fbbf24"
          className="login-point"
          style={{ animationDelay: `${i * 1.1}s` }}
        />
      ))}
    </svg>
  );
}

export default function LoginPage() {
  const [loading, setLoading] = useState(false);
  const [demoLoading, setDemoLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const errorId = useId();

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

      <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[#08090b] px-4 py-16 sm:px-6">
        {/* atmosphere: grid + ambient light + grain */}
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.06]"
          style={{
            backgroundImage:
              "linear-gradient(to right, #ffffff 1px, transparent 1px), linear-gradient(to bottom, #ffffff 1px, transparent 1px)",
            backgroundSize: "56px 56px",
            maskImage: "radial-gradient(ellipse 70% 60% at 50% 40%, black 40%, transparent 90%)",
          }}
        />
        <div
          className="login-glow pointer-events-none absolute -top-96 left-1/2 h-[36rem] w-[36rem] -translate-x-1/2 rounded-full opacity-[0.02] blur-[170px]"
          style={{ background: "radial-gradient(circle, #fbbf24 0%, transparent 60%)" }}
        />
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.03] mix-blend-overlay"
          style={{
            backgroundImage:
              "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")",
          }}
        />

        <GraphBackdrop />

        {/* card */}
        <div
          className="login-card relative w-full max-w-[29rem] rounded-[1.25rem] border border-white/[0.09] bg-[#0d0e11]/95 px-9 py-11 shadow-[0_0_0_1px_rgba(251,191,36,0.08),0_0_60px_-15px_rgba(251,191,36,0.06),0_50px_110px_-30px_rgba(0,0,0,0.95)] backdrop-blur-xl sm:px-12 sm:py-12"
        >
          <div className="mb-10 flex flex-col items-center gap-5 text-center">
            <div className="flex items-center gap-2.5">
              <TickerMark />
              <h1
                className="text-[2.35rem] leading-none font-semibold tracking-[-0.02em] text-white"
                style={{ fontFamily: "var(--font-display)" }}
              >
                Pricing Agent
              </h1>
            </div>
            <p
              className="text-[0.72rem] tracking-[0.08em] text-white/50 uppercase"
              style={{ fontFamily: "var(--font-mono)" }}
            >
              Autonomous · Always Watching
            </p>
          </div>

          {error && (
            <Alert status="danger" className="mb-6" role="alert" id={errorId}>
              <Alert.Content>
                <Alert.Description>{error}</Alert.Description>
              </Alert.Content>
            </Alert>
          )}

          <div className="flex flex-col gap-4">
            <Button
              variant="primary"
              size="lg"
              fullWidth
              onPress={handleGoogleSignIn}
              isDisabled={loading || demoLoading}
              aria-describedby={error ? errorId : undefined}
              className="group !h-12 !rounded-xl !bg-white !text-[0.92rem] !font-medium !text-black !shadow-[0_1px_0_rgba(255,255,255,0.4)_inset,0_8px_20px_-8px_rgba(0,0,0,0.5)] !transition-all !duration-200 !ease-out hover:!-translate-y-[1px] hover:!bg-white hover:!shadow-[0_1px_0_rgba(255,255,255,0.4)_inset,0_14px_28px_-10px_rgba(0,0,0,0.6)] active:!translate-y-0"
            >
              {loading ? (
                <>
                  <Spinner size="sm" /> Signing in…
                </>
              ) : (
                <>
                  <GoogleIcon />
                  Continue with Google
                </>
              )}
            </Button>

            <div className="flex items-center gap-3" role="separator" aria-orientation="horizontal">
              <span className="h-px flex-1 bg-gradient-to-r from-transparent to-white/15" />
              <span
                className="text-[0.65rem] tracking-[0.2em] text-white/35 uppercase"
                style={{ fontFamily: "var(--font-mono)" }}
              >
                or
              </span>
              <span className="h-px flex-1 bg-gradient-to-l from-transparent to-white/15" />
            </div>

            <button
              type="button"
              onClick={() => void handleDemoSignIn()}
              disabled={loading || demoLoading}
              aria-describedby={error ? errorId : undefined}
              className="group flex h-12 w-full cursor-pointer items-center justify-center gap-1.5 rounded-xl border border-white/[0.14] bg-white/[0.02] text-[0.92rem] font-medium text-white/75 transition-all duration-200 ease-out hover:-translate-y-[1px] hover:border-amber-400/40 hover:bg-white/[0.05] hover:text-white hover:shadow-[0_0_24px_-6px_rgba(251,191,36,0.35)] focus-visible:ring-2 focus-visible:ring-amber-400/50 focus-visible:outline-none disabled:pointer-events-none disabled:opacity-40"
            >
              {demoLoading ? (
                <>
                  <Spinner size="sm" /> Starting demo…
                </>
              ) : (
                <>
                  Explore without an account
                  <ArrowRightIcon
                    aria-hidden="true"
                    className="size-3.5 -translate-x-0.5 opacity-0 transition-all duration-200 group-hover:translate-x-0 group-hover:opacity-100"
                  />
                </>
              )}
            </button>
          </div>

          <p
            className="mt-8 text-center text-[0.75rem] leading-relaxed text-white/40"
            style={{ fontFamily: "var(--font-mono)" }}
          >
            Explore a fully simulated pricing dashboard.
            <br />
            No production credentials are accessed.
          </p>
        </div>
      </div>
    </>
  );
}
