"use client";

import { Clock, ExternalLink, Send, Trash2 } from "lucide-react";
import { useState } from "react";

import { Button, LinkButton } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Alert, EmptyState, ErrorState, LoadingState } from "@/components/ui/feedback";
import { Checkbox } from "@/components/ui/form";
import { Modal } from "@/components/ui/modal";
import { PageHeader } from "@/components/ui/page-header";
import { ProgressBar } from "@/components/ui/progress";
import { useToast } from "@/components/ui/toast";
import { DeadlineBadge, StatusBadge, TypeBadge } from "@/features/shared/badges";
import { useUser } from "@/features/shared/user-context";
import { api, errorMessage } from "@/lib/api";
import type { Application, ApplicationStatus } from "@/lib/types";
import { useApi } from "@/lib/use-api";

const PENDING: ApplicationStatus[] = ["to_explore", "to_prepare", "preparing"];
const SENT: ApplicationStatus[] = ["submitted", "selection", "accepted", "rejected"];

function deadlineOf(app: Application): string | null {
  return app.deadline_at ?? app.opportunity.deadline_at;
}

/**
 * Ordre de traitement : échéances les plus proches d'abord, puis les offres sans date (dans l'ordre d'ajout),
 * et en dernier les échéances déjà dépassées.
 */
export function orderQueue(apps: Application[], now: Date = new Date()): Application[] {
  const bucket = (a: Application) => {
    const d = deadlineOf(a);
    if (!d) return 1;
    return Date.parse(d) < now.getTime() ? 2 : 0;
  };
  return apps
    .filter((a) => PENDING.includes(a.status))
    .sort((a, b) => {
      const ba = bucket(a);
      const bb = bucket(b);
      if (ba !== bb) return ba - bb;
      if (ba !== 1) {
        const diff = Date.parse(deadlineOf(a)!) - Date.parse(deadlineOf(b)!);
        if (diff !== 0) return diff;
      }
      return Date.parse(a.created_at) - Date.parse(b.created_at);
    });
}

export function QueueView() {
  const user = useUser();
  const { notify } = useToast();
  const { data, error, isLoading, mutate } = useApi<Application[]>("applications");
  const [later, setLater] = useState<string[]>([]);
  const [focusId, setFocusId] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<Application | null>(null);
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false);

  if (isLoading) return <LoadingState rows={4} />;
  if (error || !data) return <ErrorState onRetry={() => mutate()} />;

  const ordered = orderQueue(data);
  // « Plus tard » : l'offre passe en fin de liste pour cette session.
  const queue = [...ordered.filter((a) => !later.includes(a.id)), ...later.map((id) => ordered.find((a) => a.id === id)).filter((a): a is Application => Boolean(a))];
  const sent = data.filter((a) => SENT.includes(a.status)).length;
  const total = sent + queue.length;
  const current = queue.find((a) => a.id === focusId) ?? queue[0];

  async function setStatus(app: Application, status: ApplicationStatus, confirm: boolean, message: string) {
    setBusy(true);
    try {
      await api(`applications/${app.id}`, { method: "PATCH", json: { status, confirm_submission: confirm } });
      notify(message);
      setFocusId(null);
      await mutate();
    } catch (err) {
      notify(errorMessage(err), "error");
    } finally {
      setBusy(false);
    }
  }

  function postpone(app: Application) {
    setLater((prev) => [...prev.filter((id) => id !== app.id), app.id]);
    setFocusId(null);
  }

  return (
    <>
      <PageHeader eyebrow="Mes candidatures" title="À postuler"
        description="Vos offres enregistrées, une à la fois : ouvrez l'offre, postulez sur le site, puis marquez-la comme envoyée."
        actions={<LinkButton href="/opportunities/new" variant="secondary">Enregistrer des offres</LinkButton>} />
      {total > 0 && <ProgressBar value={Math.round((sent / total) * 100)} label={`${sent} envoyée(s) sur ${total}`} className="mb-6" />}

      {!current ? (
        <EmptyState title={sent ? "Tout est envoyé, bravo !" : "Rien à postuler pour l'instant"}
          description="Enregistrez des offres (liens LinkedIn ou autres) pour les retrouver ici."
          action={<LinkButton href="/opportunities/new">Enregistrer des offres</LinkButton>} />
      ) : (
        <Card title={current.id === queue[0]?.id ? "Prochaine offre" : "Offre choisie"}>
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap gap-1.5">
              <TypeBadge type={current.opportunity.type} />
              <DeadlineBadge at={deadlineOf(current)} status={current.deadline_at ? "confirmed" : current.opportunity.deadline_status} tz={user.timezone} />
              <StatusBadge status={current.status} />
            </div>
            <h2 className="text-3xl font-black uppercase leading-tight">{current.opportunity.title}</h2>
            <p className="font-semibold">{current.opportunity.organization}</p>
            {current.notes && <p className="whitespace-pre-line text-sm">{current.notes}</p>}
            {(current.opportunity.organization === "À préciser" || current.opportunity.title.startsWith("Offre LinkedIn n°")) && (
              <Alert tone="info" action={<LinkButton href={`/opportunities/${current.opportunity.id}/edit`} size="sm" variant="secondary">Compléter</LinkButton>}>
                Intitulé ou entreprise à compléter après avoir ouvert l&apos;offre.
              </Alert>
            )}
            <div className="flex flex-wrap gap-2">
              <LinkButton href={current.opportunity.official_url} external variant="primary" icon={<ExternalLink className="size-4" aria-hidden />}>Ouvrir l&apos;offre</LinkButton>
              <Button variant="ink" onClick={() => { setChecked(false); setConfirming(current); }} icon={<Send className="size-4" aria-hidden />}>J&apos;ai postulé</Button>
              <Button variant="secondary" onClick={() => postpone(current)} icon={<Clock className="size-4" aria-hidden />}>Plus tard</Button>
              <LinkButton href={`/applications/${current.id}`} variant="secondary">Préparer</LinkButton>
              <Button variant="danger" disabled={busy} icon={<Trash2 className="size-4" aria-hidden />}
                onClick={() => { if (window.confirm(`Retirer « ${current.opportunity.title} » de votre liste ?`)) void setStatus(current, "withdrawn", false, "Offre retirée de la liste."); }}>
                Retirer
              </Button>
            </div>
          </div>
        </Card>
      )}

      {queue.length > 1 && (
        <section className="mt-8">
          <h2 className="mb-3 text-2xl font-black uppercase">Ensuite ({queue.length - 1})</h2>
          <ol className="flex flex-col gap-2">
            {queue.filter((a) => a.id !== current?.id).map((app) => (
              <li key={app.id}>
                <button type="button" onClick={() => setFocusId(app.id)}
                  className="flex w-full flex-wrap items-center justify-between gap-2 border-2 border-ink bg-paper px-3 py-2 text-left hover:bg-muted">
                  <span className="min-w-0">
                    <span className="block truncate font-bold">{app.opportunity.title}</span>
                    <span className="block text-sm text-ink-soft">{app.opportunity.organization}</span>
                  </span>
                  <DeadlineBadge at={deadlineOf(app)} status={app.deadline_at ? "confirmed" : app.opportunity.deadline_status} tz={user.timezone} />
                </button>
              </li>
            ))}
          </ol>
        </section>
      )}

      <Modal open={confirming !== null} onClose={() => setConfirming(null)} title="Candidature envoyée ?"
        description="L'application n'envoie jamais rien à votre place : confirmez que vous avez vous-même postulé."
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirming(null)}>Annuler</Button>
            <Button disabled={!checked} loading={busy}
              onClick={async () => { if (confirming) { await setStatus(confirming, "submitted", true, "Candidature marquée comme envoyée."); setConfirming(null); } }}>
              Confirmer
            </Button>
          </>
        }>
        <Checkbox label="J'ai moi-même envoyé ma candidature sur le site de l'offre" checked={checked} onChange={(e) => setChecked(e.target.checked)} />
      </Modal>
    </>
  );
}
