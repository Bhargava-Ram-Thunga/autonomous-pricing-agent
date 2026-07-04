"use client";

import { useState } from "react";
import { Button, Card, Alert, Separator, Spinner } from "@heroui/react";
import { ArrowRightIcon, TrendingUpIcon } from "lucide-react";

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
      <div className="bg-default flex min-h-screen items-center justify-center p-6">
        <Card className="w-full max-w-sm shadow-lg">
          <Card.Header className="flex flex-col items-center gap-2 text-center">
            <div className="bg-accent text-accent-foreground flex size-11 items-center justify-center rounded-xl">
              <TrendingUpIcon className="size-5" />
            </div>
            <Card.Title>Pricing Agent</Card.Title>
            <Card.Description>Autonomous pricing, monitored live</Card.Description>
          </Card.Header>
          <Card.Content className="flex flex-col gap-4">
            {error && (
              <Alert status="danger">
                <Alert.Content>
                  <Alert.Description>{error}</Alert.Description>
                </Alert.Content>
              </Alert>
            )}

            <Button
              variant="outline"
              size="lg"
              fullWidth
              onPress={handleGoogleSignIn}
              isDisabled={loading || demoLoading}
            >
              <GoogleIcon />
              {loading ? (
                <>
                  <Spinner size="sm" /> Signing in…
                </>
              ) : (
                "Sign in with Google"
              )}
            </Button>

            <div className="flex items-center gap-3">
              <Separator className="flex-1" />
              <span className="text-muted text-xs tracking-wide uppercase">or</span>
              <Separator className="flex-1" />
            </div>

            <Button
              variant="primary"
              size="lg"
              fullWidth
              onPress={handleDemoSignIn}
              isDisabled={loading || demoLoading}
            >
              {demoLoading ? (
                <>
                  <Spinner size="sm" /> Starting demo…
                </>
              ) : (
                <>
                  Continue with Demo Access
                  <ArrowRightIcon className="size-4" />
                </>
              )}
            </Button>

            <p className="text-muted text-center text-xs leading-relaxed">
              Demo access skips Google auth for local evaluation. No real portal
              credentials are used.
            </p>
          </Card.Content>
        </Card>
      </div>
    </>
  );
}
