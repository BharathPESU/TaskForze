"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "./AuthProvider";

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [user, loading, router]);

  if (loading || !user) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-[#0b0c10]">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-[#2a2b36] bg-[#1e1f2a]">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-[#7b61ff] border-r-transparent" />
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
