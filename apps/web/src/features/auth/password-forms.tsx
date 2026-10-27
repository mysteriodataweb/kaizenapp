"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/feedback";
import { Field, FormError, Input } from "@/components/ui/form";
import { api, errorMessage } from "@/lib/api";
import { newPasswordSchema } from "./schemas";

const emailSchema = z.object({ email: z.email("Adresse e-mail invalide.") });

export function ForgotPasswordForm() {
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm<z.infer<typeof emailSchema>>({ resolver: zodResolver(emailSchema) });
  async function onSubmit(values: z.infer<typeof emailSchema>) {
    setError(null);
    try {
      const res = await api<{ message: string }>("auth/password-reset/request", { method: "POST", json: values });
      setDone(res.message);
    } catch (err) {
      setError(errorMessage(err));
    }
  }
  return (
    <div className="brutal-card p-6 sm:p-8">
      <h1 className="text-4xl font-black uppercase leading-none">Mot de passe oublié</h1>
      <p className="mt-2 text-sm text-ink-soft">Un lien valable 30 minutes vous sera envoyé si un compte correspond.</p>
      {done ? (
        <Alert tone="success" className="mt-6">{done}</Alert>
      ) : (
        <form onSubmit={handleSubmit(onSubmit)} noValidate className="mt-6 flex flex-col gap-4">
          <Field label="Adresse e-mail" error={formState.errors.email?.message} required>
            {(p) => <Input {...p} type="email" autoComplete="email" {...register("email")} />}
          </Field>
          <FormError message={error} />
          <Button type="submit" loading={formState.isSubmitting}>Envoyer le lien</Button>
        </form>
      )}
      <Link href="/login" className="mt-4 block text-center text-sm font-bold underline underline-offset-4">Retour à la connexion</Link>
    </div>
  );
}

export function ResetPasswordForm() {
  const token = useSearchParams().get("token") ?? "";
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm<z.infer<typeof newPasswordSchema>>({ resolver: zodResolver(newPasswordSchema) });
  async function onSubmit(values: z.infer<typeof newPasswordSchema>) {
    setError(null);
    try {
      await api("auth/password-reset/confirm", { method: "POST", json: { token, new_password: values.password } });
      setDone(true);
    } catch (err) {
      setError(errorMessage(err));
    }
  }
  if (!token) return <Alert tone="danger" title="Lien invalide">Ce lien de réinitialisation est incomplet.</Alert>;
  return (
    <div className="brutal-card p-6 sm:p-8">
      <h1 className="text-4xl font-black uppercase leading-none">Nouveau mot de passe</h1>
      {done ? (
        <Alert tone="success" className="mt-6" title="Mot de passe modifié">
          Toutes vos sessions ont été fermées. <Link href="/login" className="font-bold underline">Se connecter</Link>
        </Alert>
      ) : (
        <form onSubmit={handleSubmit(onSubmit)} noValidate className="mt-6 flex flex-col gap-4">
          <Field label="Nouveau mot de passe" hint="12 caractères minimum." error={formState.errors.password?.message} required>
            {(p) => <Input {...p} type="password" autoComplete="new-password" {...register("password")} />}
          </Field>
          <Field label="Confirmation" error={formState.errors.confirm?.message} required>
            {(p) => <Input {...p} type="password" autoComplete="new-password" {...register("confirm")} />}
          </Field>
          <FormError message={error} />
          <Button type="submit" loading={formState.isSubmitting}>Enregistrer</Button>
        </form>
      )}
    </div>
  );
}
