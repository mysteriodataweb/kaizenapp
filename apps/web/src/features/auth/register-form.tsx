"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { MailCheck, UserPlus } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Alert, LoadingState } from "@/components/ui/feedback";
import { Checkbox, Field, FormError, Input } from "@/components/ui/form";
import { api, errorMessage } from "@/lib/api";
import type { AuthConfig } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { type RegisterValues, registerSchema } from "./schemas";

export function RegisterForm() {
  const { data: config, isLoading } = useApi<AuthConfig>("auth/config");
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { display_name: "", accept: false },
  });

  async function onSubmit(values: RegisterValues) {
    setError(null);
    try {
      const res = await api<{ message: string }>("auth/register", {
        method: "POST",
        json: { email: values.email, password: values.password, display_name: values.display_name || null },
      });
      setDone(res.message);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <div className="brutal-card p-6 sm:p-8">
      <h1 className="text-5xl font-black uppercase leading-none">Inscription</h1>
      <p className="mt-2 text-sm text-ink-soft">Créez votre espace pour suivre stages et bourses de master. Vos données ne sont visibles que par vous.</p>
      {isLoading ? (
        <div className="mt-6"><LoadingState rows={2} /></div>
      ) : !config?.registration_open ? (
        <Alert tone="info" className="mt-6" title="Inscriptions fermées">
          Les inscriptions ne sont pas ouvertes pour le moment. Si vous avez déjà un compte, connectez-vous.
        </Alert>
      ) : done ? (
        <Alert tone="success" className="mt-6" title="Vérifiez votre boîte e-mail">{done}</Alert>
      ) : (
        <form onSubmit={handleSubmit(onSubmit)} noValidate className="mt-6 flex flex-col gap-4">
          <Field label="Nom affiché" hint="Facultatif." error={formState.errors.display_name?.message}>
            {(p) => <Input {...p} autoComplete="name" maxLength={200} {...register("display_name")} />}
          </Field>
          <Field label="Adresse e-mail" hint="Un lien de confirmation y sera envoyé." error={formState.errors.email?.message} required>
            {(p) => <Input {...p} type="email" autoComplete="email" {...register("email")} />}
          </Field>
          <Field label="Mot de passe" hint="12 caractères minimum." error={formState.errors.password?.message} required>
            {(p) => <Input {...p} type="password" autoComplete="new-password" {...register("password")} />}
          </Field>
          <Field label="Confirmation" error={formState.errors.confirm?.message} required>
            {(p) => <Input {...p} type="password" autoComplete="new-password" {...register("confirm")} />}
          </Field>
          <div>
            <Checkbox
              label="J'accepte que mes informations soient enregistrées pour faire fonctionner le service."
              description="Profil, candidatures et documents servent uniquement au matching et au suivi. Vous pouvez supprimer votre compte et toutes vos données à tout moment (Paramètres)."
              aria-invalid={formState.errors.accept ? true : undefined}
              {...register("accept")}
            />
            {formState.errors.accept && <p role="alert" className="mt-1 text-sm font-semibold text-danger">{formState.errors.accept.message}</p>}
          </div>
          <FormError message={error} />
          <Button type="submit" size="lg" loading={formState.isSubmitting} icon={<UserPlus className="size-5" aria-hidden />}>
            Créer mon compte
          </Button>
        </form>
      )}
      <Link href="/login" className="mt-4 block text-center text-sm font-bold underline underline-offset-4">Déjà un compte ? Se connecter</Link>
    </div>
  );
}

/** Confirmation explicite par un clic : les scanners de liens des messageries ne valident pas le compte à la place de l'utilisateur. */
export function VerifyEmailForm() {
  const token = useSearchParams().get("token") ?? "";
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function confirm() {
    setError(null);
    setLoading(true);
    try {
      const res = await api<{ message: string }>("auth/verify-email", { method: "POST", json: { token } });
      setDone(res.message);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="brutal-card p-6 sm:p-8">
      <h1 className="text-4xl font-black uppercase leading-none">Confirmer l&apos;adresse</h1>
      {!token ? (
        <Alert tone="danger" className="mt-6" title="Lien invalide">Ce lien de confirmation est incomplet.</Alert>
      ) : done ? (
        <Alert tone="success" className="mt-6" title="Adresse confirmée">
          {done} <Link href="/login" className="font-bold underline">Se connecter</Link>
        </Alert>
      ) : (
        <div className="mt-6 flex flex-col gap-4">
          <p className="text-sm text-ink-soft">Cliquez sur le bouton pour activer votre compte.</p>
          <FormError message={error} />
          <Button size="lg" onClick={confirm} loading={loading} icon={<MailCheck className="size-5" aria-hidden />}>
            Confirmer mon adresse
          </Button>
          {error && <ResendVerification />}
        </div>
      )}
    </div>
  );
}

/** Nouvel envoi du lien (réponse identique que le compte existe ou non). */
export function ResendVerification({ email: initialEmail = "" }: { email?: string }) {
  const [email, setEmail] = useState(initialEmail);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function resend() {
    setError(null);
    setLoading(true);
    try {
      const res = await api<{ message: string }>("auth/verify-email/resend", { method: "POST", json: { email } });
      setMessage(res.message);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  if (message) return <Alert tone="success">{message}</Alert>;
  return (
    <div className="flex flex-col gap-3 border-2 border-dashed border-ink p-3">
      <Field label="Recevoir un nouveau lien de confirmation">
        {(p) => <Input {...p} type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />}
      </Field>
      <FormError message={error} />
      <Button variant="secondary" size="sm" className="self-start" onClick={resend} loading={loading} disabled={!email.includes("@")}>
        Renvoyer le lien
      </Button>
    </div>
  );
}
