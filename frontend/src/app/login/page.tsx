"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { signInWithPopup } from "firebase/auth";
import { auth, googleProvider } from "@/lib/firebase";
import { useAuth } from "@/components/AuthProvider";
import { Layout, ShieldAlert } from "lucide-react";
import Image from "next/image";

export default function LoginPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [isSigningIn, setIsSigningIn] = useState(false);

  useEffect(() => {
    if (!loading && user) {
      router.replace("/");
    }
  }, [user, loading, router]);

  const handleGoogleSignIn = async () => {
    try {
      setIsSigningIn(true);
      setError(null);
      await signInWithPopup(auth, googleProvider);
      // Successful sign in will trigger the useEffect above to redirect
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to sign in";
      setError(message);
      setIsSigningIn(false);
    }
  };

  if (loading || user) {
    return null; // Will redirect or show loading in AuthGuard if used there
  }

  return (
    <div className="flex h-screen w-full flex-col items-center justify-center bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-[#1d1b32] via-[#0b0c10] to-[#0b0c10] text-[#e2e8f0]">
      <div className="w-full max-w-md px-8 text-center mt-[-10vh]">
        <div className="mb-8 flex justify-center">
          <div className="relative h-28 w-28 drop-shadow-[0_0_40px_rgba(123,97,255,0.4)]">
            <Image src="/logo.png" alt="TaskForze Logo" fill priority className="object-contain" />
          </div>
        </div>

        <h1 className="mb-3 text-4xl font-bold tracking-tight text-white">
          TaskForze
        </h1>
        <p className="mb-10 text-lg leading-relaxed text-[#94a3b8]">
          Your personal AI workforce. Delegate tasks, orchestrate workflows, and 
          multiply your productivity.
        </p>

        {error && (
          <div className="mb-6 flex items-start gap-3 rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-left text-sm text-rose-200">
            <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-rose-400" />
            <span className="leading-relaxed">{error}</span>
          </div>
        )}

        <button
          onClick={handleGoogleSignIn}
          disabled={isSigningIn}
          className="group relative flex w-full items-center justify-center gap-3 overflow-hidden rounded-2xl bg-white px-6 py-4 text-base font-medium text-black transition-transform hover:scale-[1.02] active:scale-[0.98] disabled:opacity-70 disabled:hover:scale-100"
        >
          <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/50 to-transparent opacity-0 transition-opacity group-hover:opacity-100" />
          {isSigningIn ? (
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-black border-r-transparent" />
          ) : (
            <svg className="h-5 w-5" viewBox="0 0 24 24">
              <path
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                fill="#4285F4"
              />
              <path
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                fill="#34A853"
              />
              <path
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                fill="#FBBC05"
              />
              <path
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                fill="#EA4335"
              />
            </svg>
          )}
          <span>{isSigningIn ? "Signing in..." : "Continue with Google"}</span>
        </button>

        <p className="mt-8 text-sm text-[#47516b]">
          Secured by Google Authentication
        </p>
      </div>
    </div>
  );
}
