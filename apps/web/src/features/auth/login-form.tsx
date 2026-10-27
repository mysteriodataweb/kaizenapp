"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { LogIn } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/feedback";
import { Field, FormError, Input } from "@/components/ui/form";
import { t } from "@/i18n";
import type { AuthConfig } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { ResendVerification } from "./register-form";
import { type LoginValues, loginSchema } from "./schemas";

export function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const [unverifiedEmail, setUnverifiedEmail] = useState<string | null>(null);
  const { data: config } = useApi<AuthConfig>("auth/config");
  const { register, handleSubmit, formState } = useForm<LoginValues>({ resolver: zodResolver(loginSchema) });

  async function onSubmit(values: LoginValues) {
    setError(null);
    setUnverifiedEmail(null);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(values),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        setError(body?.error?.message ?? t.common.error);
        if (body?.error?.code === "email_not_verified") setUnverifiedEmail(values.email);
        return;
      }
      const next = params.get("next");
      router.replace(next && next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard");
      router.refresh();
    } catch {
      setError(t.common.networkError);
    }
  }

  return (
    <div className="brutal-card p-6 sm:p-8">
      <p className="mb-1 inline-block bg-accent px-1.5 text-xs font-bold uppercase tracking-widest lg:hidden">{t.app.name}</p>
      <h1 className="text-5xl font-black uppercase leading-none">Connexion</h1>
      <p className="mt-2 text-sm text-ink-soft">Accédez à votre espace de veille : stages, bourses de master et candidatures.</p>
      {params.get("expired") && (
        <Alert tone="warning" className="mt-4">Votre session a expiré. Reconnectez-vous.</Alert>
      )}
      {params.get("deleted") && (
        <Alert tone="success" className="mt-4">Votre compte et toutes vos données ont été supprimés.</Alert>
      )}
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="mt-6 flex flex-col gap-4">
        <Field label="Adresse e-mail" error={formState.errors.email?.message} required>
          {(p) => <Input {...p} type="email" autoComplete="email" {...register("email")} />}
        </Field>
        <Field label="Mot de passe" error={formState.errors.password?.message} required>
          {(p) => <Input {...p} type="password" autoComplete="current-password" {...register("password")} />}
        </Field>
        <FormError message={error} />
        {unverifiedEmail && <ResendVerification email={unverifiedEmail} />}
        <Button type="submit" size="lg" loading={formState.isSubmitting} icon={<LogIn className="size-5" aria-hidden />}>
          Se connecter
        </Button>
        <Link href="/forgot-password" className="text-center text-sm font-bold underline underline-offset-4">Mot de passe oublié ?</Link>
      </form>
      {config?.registration_open && (
        <p className="mt-6 border-t-2 border-ink pt-4 text-center text-sm">
          Pas encore de compte ?{" "}
          <Link href="/register" className="font-bold underline underline-offset-4">Créer un compte</Link>
        </p>
      )}
    </div>
  );
}
