"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Eye, Send } from "lucide-react";
import { useEffect, useState } from "react";
import { Controller, type Resolver, useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { type Column, DataTable } from "@/components/ui/data-table";
import { Alert, EmptyState, ErrorState, LoadingState } from "@/components/ui/feedback";
import { Checkbox, Field, FormError, Input, Select } from "@/components/ui/form";
import { Modal } from "@/components/ui/modal";
import { PageHeader } from "@/components/ui/page-header";
import { useToast } from "@/components/ui/toast";
import { useUser } from "@/features/shared/user-context";
import { label, t } from "@/i18n";
import { api, errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { NotificationLog, NotificationPreview, NotificationPrefs } from "@/lib/types";
import { useApi } from "@/lib/use-api";

const REMINDERS = [30, 14, 7, 3, 1, 0];

const schema = z.object({
  email: z.email("E-mail invalide").or(z.literal("")),
  enabled: z.boolean(),
  digest_frequency: z.enum(["daily", "weekly", "never"]),
  digest_weekday: z.number().int().min(0).max(6),
  digest_hour: z.number().int().min(0).max(23),
  notify_new_matches: z.boolean(),
  notify_deadlines: z.boolean(),
  notify_tasks: z.boolean(),
  notify_changes: z.boolean(),
  notify_ingestion_errors: z.boolean(),
  min_score: z.number().int().min(0).max(100),
  max_items: z.number().int().min(1).max(50),
  deadline_reminder_days: z.array(z.number().int().min(0).max(90)).max(8),
});
type Values = z.infer<typeof schema>;

export function NotificationsView() {
  const user = useUser();
  const { notify } = useToast();
  const { data: prefs, error, isLoading, mutate } = useApi<NotificationPrefs>("notifications/preferences");
  const { data: logs, mutate: mutateLogs } = useApi<NotificationLog[]>("notifications/logs");
  const [serverError, setServerError] = useState<string | null>(null);
  const [preview, setPreview] = useState<NotificationPreview | null>(null);
  const [testOpen, setTestOpen] = useState(false);
  const form = useForm<Values>({ resolver: zodResolver(schema) as Resolver<Values> });
  const { register, control, handleSubmit, reset, formState } = form;
  const frequency = useWatch({ control, name: "digest_frequency" });
  useEffect(() => {
    if (prefs) reset({ ...prefs, email: prefs.email ?? "" });
  }, [prefs, reset]);

  if (isLoading) return <LoadingState rows={4} />;
  if (error || !prefs) return <ErrorState onRetry={() => mutate()} />;

  async function onSubmit(values: Values) {
    setServerError(null);
    try {
      const saved = await api<NotificationPrefs>("notifications/preferences", { method: "PUT", json: { ...values, email: values.email || null } });
      await mutate(saved, { revalidate: false });
      notify(t.common.saved);
    } catch (err) {
      setServerError(errorMessage(err));
    }
  }

  async function showPreview(kind: string) {
    try {
      setPreview(await api<NotificationPreview>(`notifications/preview?kind=${kind}`));
    } catch (err) {
      notify(errorMessage(err), "error");
    }
  }

  async function sendTest() {
    try {
      const log = await api<NotificationLog>("notifications/test", { method: "POST", json: { confirm: true } });
      notify(log.status === "simulated" ? "E-mail simulé (mode test : rien n'a été envoyé)." : `E-mail ${label(t.notificationStatus, log.status)}.`, log.status === "failed" ? "error" : "success");
      setTestOpen(false);
      await mutateLogs();
    } catch (err) {
      notify(errorMessage(err), "error");
    }
  }

  const columns: Column<NotificationLog>[] = [
    { key: "date", header: "Date", cell: (l) => formatDate(l.created_at, user.timezone, true) },
    { key: "kind", header: "Type", cell: (l) => label(t.notificationKind, l.kind) },
    { key: "subject", header: "Objet", cell: (l) => <span className="font-semibold">{l.subject}</span> },
    { key: "status", header: "Statut", cell: (l) => (
      <Badge tone={l.status === "sent" ? "success" : l.status === "failed" ? "danger" : l.status === "simulated" ? "accent" : "neutral"}>{label(t.notificationStatus, l.status)}</Badge>
    ) },
    { key: "attempts", header: "Tentatives", cell: (l) => l.attempts, mobile: false },
    { key: "error", header: "Erreur", cell: (l) => l.last_error ?? "—", mobile: false },
  ];

  return (
    <>
      <PageHeader eyebrow="E-mails" title={t.nav.notifications} description="Alertes dédupliquées : une même notification n'est jamais envoyée deux fois. Aucun rappel n'est envoyé pour une date inconnue." />
      {prefs.email_mode === "simulation" && (
        <Alert tone="warning" className="mb-6" title="Mode simulation : les e-mails réels ne sont pas actifs">
          RESEND_API_KEY et EMAIL_FROM ne sont pas configurés côté serveur. Les alertes sont générées et journalisées, mais aucun e-mail n&apos;est envoyé.
        </Alert>
      )}
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="grid gap-6 xl:grid-cols-2">
        <Card title="Destinataire & fréquence">
          <div className="flex flex-col gap-4">
            <Checkbox label="Activer les alertes e-mail" {...register("enabled")} />
            <Field label="Adresse e-mail" hint={`Destinataire effectif : ${prefs.effective_recipient ?? "aucun (adresse non autorisée)"}. Seules l'adresse du compte et les adresses autorisées côté serveur sont acceptées.`} error={formState.errors.email?.message}>
              {(p) => <Input {...p} type="email" {...register("email")} />}
            </Field>
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="Récapitulatif">{(p) => (
                <Select {...p} {...register("digest_frequency")}>
                  {Object.entries(t.digestFrequency).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </Select>
              )}</Field>
              <Field label="Jour">{(p) => (
                <Select {...p} disabled={frequency !== "weekly"} {...register("digest_weekday", { valueAsNumber: true })}>
                  {t.weekdays.map((d, i) => <option key={d} value={i}>{d}</option>)}
                </Select>
              )}</Field>
              <Field label="Heure (locale)">{(p) => (
                <Select {...p} disabled={frequency === "never"} {...register("digest_hour", { valueAsNumber: true })}>
                  {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{String(h).padStart(2, "0")} h</option>)}
                </Select>
              )}</Field>
            </div>
          </div>
        </Card>
        <Card title="Types d'alertes">
          <div className="flex flex-col gap-3">
            <Checkbox label="Nouvelles opportunités compatibles" {...register("notify_new_matches")} />
            <Checkbox label="Rappels d'échéance" description="Les dates non vérifiées sont signalées comme telles." {...register("notify_deadlines")} />
            <Checkbox label="Tâches à effectuer" {...register("notify_tasks")} />
            <Checkbox label="Opportunités suivies modifiées" {...register("notify_changes")} />
            {user.is_admin && <Checkbox label="Erreurs répétées de collecte" {...register("notify_ingestion_errors")} />}
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Score minimal" hint="0 à 100">{(p) => <Input {...p} type="number" min={0} max={100} {...register("min_score", { valueAsNumber: true })} />}</Field>
              <Field label="Offres max. par résumé">{(p) => <Input {...p} type="number" min={1} max={50} {...register("max_items", { valueAsNumber: true })} />}</Field>
            </div>
            <Controller control={control} name="deadline_reminder_days" render={({ field }) => (
              <fieldset>
                <legend className="mb-2 text-sm font-bold">Rappels avant échéance</legend>
                <div className="flex flex-wrap gap-2">
                  {REMINDERS.map((d) => {
                    const on = field.value?.includes(d);
                    return (
                      <button key={d} type="button" aria-pressed={on} onClick={() => field.onChange(on ? field.value.filter((x) => x !== d) : [...(field.value ?? []), d])}
                        className={`h-9 border-2 border-ink px-3 text-sm font-bold ${on ? "bg-accent shadow-[var(--shadow-brutal-sm)]" : "bg-paper"}`}>
                        {d === 0 ? "Jour J" : `J-${d}`}
                      </button>
                    );
                  })}
                </div>
              </fieldset>
            )} />
          </div>
        </Card>
        <div className="flex flex-wrap items-center gap-3 xl:col-span-2">
          <Button type="submit" loading={formState.isSubmitting}>{t.common.save}</Button>
          <Button variant="secondary" onClick={() => showPreview("digest")} icon={<Eye className="size-4" aria-hidden />}>Aperçu du récapitulatif</Button>
          <Button variant="secondary" onClick={() => showPreview("new_matches")} icon={<Eye className="size-4" aria-hidden />}>Aperçu nouvelles offres</Button>
          <Button variant="secondary" onClick={() => showPreview("deadline")} icon={<Eye className="size-4" aria-hidden />}>Aperçu rappels</Button>
          <Button variant="ink" onClick={() => setTestOpen(true)} icon={<Send className="size-4" aria-hidden />}>E-mail de test</Button>
          <FormError message={serverError} />
        </div>
      </form>

      <section className="mt-8">
        <h2 className="mb-3 text-2xl font-black uppercase">Journal d&apos;envoi</h2>
        <DataTable rows={logs ?? []} columns={columns} rowKey={(l) => l.id} caption="Journal des notifications"
          empty={<EmptyState title="Aucun e-mail" description="Les notifications envoyées ou simulées apparaîtront ici." />} />
      </section>

      <Modal open={testOpen} onClose={() => setTestOpen(false)} title="Envoyer un e-mail de test ?"
        description={`Destinataire : ${prefs.effective_recipient ?? "aucun"}. ${prefs.email_mode === "simulation" ? "Mode simulation : rien ne sera réellement envoyé." : "Un e-mail réel sera envoyé via Resend."}`}
        footer={<><Button variant="secondary" onClick={() => setTestOpen(false)}>{t.common.cancel}</Button><Button onClick={sendTest} disabled={!prefs.effective_recipient}>{t.common.confirm}</Button></>} />

      <Modal open={preview !== null} onClose={() => setPreview(null)} title={preview?.subject ?? "Aperçu"} description={preview?.note ?? `${preview?.items ?? 0} élément(s) — aperçu, rien n'est envoyé.`}>
        {preview && <iframe title="Aperçu de l'e-mail" srcDoc={preview.html} sandbox="" className="h-[60vh] w-full border-2 border-ink" />}
      </Modal>
    </>
  );
}
