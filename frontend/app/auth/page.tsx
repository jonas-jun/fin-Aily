"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Auth } from "@supabase/auth-ui-react";
import { ThemeSupa } from "@supabase/auth-ui-shared";
import { createClient } from "@/lib/supabase";
import { Logo } from "@/components/ui/Logo";

export default function AuthPage() {
  const router = useRouter();
  const supabase = createClient();

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      if (data.session) router.replace("/");
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange((event) => {
      if (event === "SIGNED_IN") router.replace("/");
    });

    return () => subscription.unsubscribe();
  }, []);

  return (
    <div className="flex justify-center pt-10">
      <div className="w-full max-w-sm rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="mb-6 flex flex-col items-center gap-2">
          <Logo size="sm" />
          <p className="text-sm text-slate-500 mt-1">Sign in to use your watchlist</p>
        </div>
        <Auth
          supabaseClient={supabase}
          appearance={{ theme: ThemeSupa }}
          providers={["google"]}
          localization={{
            variables: {
              sign_in: { email_label: "Email", password_label: "Password", button_label: "Sign in" },
              sign_up: { email_label: "Email", password_label: "Password", button_label: "Sign up" },
            },
          }}
        />
      </div>
    </div>
  );
}
