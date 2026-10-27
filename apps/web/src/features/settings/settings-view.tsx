"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field, FormError, Input, Select } from "@/components/ui/form";
import { Modal } from "@/components/ui/modal";
import { PageHeader } from "@/components/ui/page-header";
import { useToast } from "@/components/ui/toast";
import { useUser } from "@/features/shared/user-context";
import { t } from "@/i18n";
import { api, errorMessage } from "@/lib/api";

const passwordSchema = z
  .object({ current_password: z.string().min(1, "Requis"), new_password: z.string().min(12, "12 caractères minimum."), confirm: z.string() })
  .refine((v) => v.new_password === v.confirm, { path: ["confirm"], message: "Les mots de passe ne correspondent pas." });

export function SettingsView() {
  const user = useUser();
  const router = useRouter();
  const { notify } = useToast();
  const zones = useMemo(() => (typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [user.timezone]), [user.timezone]);
  const [displayName, setDisplayName] = useState(user.display_name ?? "");
  const [timezone, setTimezone] = useState(user.timezone);
  const [accountError, setAccountError] = useState<string | null>(null);
  const [savingAccount, setSavingAccount] = useState(false);
  const pw = useForm<z.infer<typeof passwordSchema>>({ resolver: zodResolver(passwordSchema) });
  const [pwError, setPwError] = useState<string | null>(null);

  async function saveAccount() {
    setSavingAccount(true);
    setAccountError(null);
    try {
      await api("auth/me", { method: "PATCH", json: { display_name: displayName || null, timezone } });
      notify(t.common.saved);
      router.refresh();
    } catch (err) {
      setAccountError(errorMessage(err));
    } finally {
      setSavingAccount(false);
    }
  }

  async function changePassword(values: z.infer<typeof passwordSchema>) {
    setPwError(null);
    try {
      await api("auth/change-password", { method: "POST", json: { current_password: values.current_password, new_password: values.new_password } });
      pw.reset();
      notify("Mot de passe modifié. Vos autres sessions ont été fermées.");
    } catch (err) {
      setPwError(errorMessage(err));
    }
  }

  async function logoutOthers() {
    try {
      const res = await api<{ message: string }>("auth/logout-all", { method: "POST" });
      notify(res.message);
    } catch (err) {
      notify(errorMessage(err), "error");
    }
  }

  return (
    <>
      <PageHeader eyebrow="Compte" title={t.nav.settings} />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Compte">
          <div className="flex flex-col gap-4">
            <Field label="Adresse e-mail" hint="Identifiant de connexion (non modifiable ici).">{(p) => <Input {...p} value={user.email} disabled />}</Field>
            <Field label="Nom affiché">{(p) => <Input {...p} value={displayName} onChange={(e) => setDisplayName(e.target.value)} maxLength={200} />}</Field>
            <Field label="Fuseau horaire" hint="Toutes les dates et échéances sont interprétées dans ce fuseau.">{(p) => (
              <Select {...p} value={timezone} onChange={(e) => setTimezone(e.target.value)}>
                {zones.map((z) => <option key={z} value={z}>{z}</option>)}
              </Select>
            )}</Field>
            <Field label="Langue de l'interface" hint="Anglais prévu ultérieurement.">{(p) => (
              <Select {...p} value="fr" disabled><option value="fr">Français</option></Select>
            )}</Field>
            <FormError message={accountError} />
            <Button className="self-start" onClick={saveAccount} loading={savingAccount}>{t.common.save}</Button>
          </div>
        </Card>
        <div className="flex flex-col gap-6">
          <Card title="Mot de passe">
            <form onSubmit={pw.handleSubmit(changePassword)} noValidate className="flex flex-col gap-4">
              <Field label="Mot de passe actuel" error={pw.formState.errors.current_password?.message}>{(p) => <Input {...p} type="password" autoComplete="current-password" {...pw.register("current_password")} />}</Field>
              <Field label="Nouveau mot de passe" error={pw.formState.errors.new_password?.message}>{(p) => <Input {...p} type="password" autoComplete="new-password" {...pw.register("new_password")} />}</Field>
              <Field label="Confirmation" error={pw.formState.errors.confirm?.message}>{(p) => <Input {...p} type="password" autoComplete="new-password" {...pw.register("confirm")} />}</Field>
              <FormError message={pwError} />
              <Button type="submit" className="self-start" loading={pw.formState.isSubmitting}>Modifier le mot de passe</Button>
            </form>
          </Card>
          <Card title="Sessions">
            <p className="mb-3 text-sm text-ink-soft">Déconnecte tous les autres appareils (la session actuelle reste ouverte).</p>
            <Button variant="danger" onClick={logoutOthers}>Fermer les autres sessions</Button>
          </Card>
          <DeleteAccountCard />
        </div>
      </div>
    </>
  );
}

const CONFIRM_WORD = "SUPPRIMER";

function DeleteAccountCard() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [word, setWord] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function close() {
    setOpen(false);
    setPassword("");
    setWord("");
    setError(null);
  }

  async function remove() {
    setError(null);
    setLoading(true);
    try {
      await api("auth/delete-account", { method: "POST", json: { password } });
      await fetch("/api/auth/logout", { method: "POST" }).catch(() => undefined);
      router.replace("/login?deleted=1");
      router.refresh();
    } catch (err) {
      setError(errorMessage(err));
      setLoading(false);
    }
  }

  return (
    <Card title="Supprimer mon compte">
      <p className="mb-3 text-sm text-ink-soft">
        Supprime définitivement votre compte, votre profil, vos candidatures, tâches, documents et historique d&apos;alertes. Action irréversible.
      </p>
      <Button variant="danger" onClick={() => setOpen(true)}>Supprimer mon compte…</Button>
      <Modal open={open} onClose={close} title="Supprimer le compte"
        description="Toutes vos données seront effacées immédiatement et ne pourront pas être récupérées."
        footer={
          <>
            <Button variant="secondary" onClick={close}>Annuler</Button>
            <Button variant="danger" onClick={remove} loading={loading} disabled={!password || word !== CONFIRM_WORD}>Supprimer définitivement</Button>
          </>
        }>
        <div className="flex flex-col gap-4">
          <Field label="Mot de passe actuel">{(p) => <Input {...p} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />}</Field>
          <Field label={`Tapez ${CONFIRM_WORD} pour confirmer`}>{(p) => <Input {...p} value={word} onChange={(e) => setWord(e.target.value)} autoComplete="off" />}</Field>
          <FormError message={error} />
        </div>
      </Modal>
    </Card>
  );
}
