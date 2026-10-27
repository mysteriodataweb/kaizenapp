"use client";

import { ArrowLeft, Check, ExternalLink, Link2, Plus, Trash2, Unlink } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button, LinkButton } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Alert, ErrorState, LoadingState } from "@/components/ui/feedback";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { Modal } from "@/components/ui/modal";
import { ScoreMeter } from "@/components/ui/progress";
import { useToast } from "@/components/ui/toast";
import { AssistPanel } from "@/features/assist/assist-panel";
import { DeadlineBadge, EligibilityBadge, StatusBadge, UrgencyBadge } from "@/features/shared/badges";
import { useUser } from "@/features/shared/user-context";
import { label, t } from "@/i18n";
import { ApiError, api, errorMessage } from "@/lib/api";
import { formatDate, isoToLocalInput, localInputToIso } from "@/lib/format";
import type { Application, ApplicationEvent, DocumentItem, Task } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { StatusControl } from "./status-control";

const EVENT_LABELS: Record<string, string> = {
  created: "Ajoutée au suivi",
  status_changed: "Statut modifié",
  fields_updated: "Informations modifiées",
  document_linked: "Document associé",
  document_unlinked: "Document retiré",
  task_created: "Tâche créée",
};

type FormState = Record<"deadline_at" | "contact_name" | "contact_email" | "next_action" | "next_action_at" | "follow_up_at" | "estimated_prep_hours" | "notes" | "response_notes" | "response_received_at" | "submitted_at", string>;

function toForm(a: Application): FormState {
  return {
    deadline_at: isoToLocalInput(a.deadline_at),
    contact_name: a.contact_name ?? "",
    contact_email: a.contact_email ?? "",
    next_action: a.next_action ?? "",
    next_action_at: isoToLocalInput(a.next_action_at),
    follow_up_at: isoToLocalInput(a.follow_up_at),
    estimated_prep_hours: a.estimated_prep_hours?.toString() ?? "",
    notes: a.notes ?? "",
    response_notes: a.response_notes ?? "",
    response_received_at: isoToLocalInput(a.response_received_at),
    submitted_at: isoToLocalInput(a.submitted_at),
  };
}

export function ApplicationDetailView({ id }: { id: string }) {
  const user = useUser();
  const tz = user.timezone;
  const router = useRouter();
  const { notify } = useToast();
  const { data: app, error, isLoading, mutate } = useApi<Application>(`applications/${id}`);
  const { data: events, mutate: mutateEvents } = useApi<ApplicationEvent[]>(`applications/${id}/events`);
  const { data: tasks, mutate: mutateTasks } = useApi<Task[]>(`tasks?application_id=${id}&include_done=true`);
  const { data: documents } = useApi<DocumentItem[]>("documents");
  const [form, setForm] = useState<FormState | null>(null);
  const [saving, setSaving] = useState(false);
  const [taskTitle, setTaskTitle] = useState("");
  const [taskDue, setTaskDue] = useState("");
  const [docToLink, setDocToLink] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);

  // Réinitialise le formulaire quand la candidature chargée change (état dérivé, sans effet).
  const [formSource, setFormSource] = useState<Application | undefined>(undefined);
  if (app && app !== formSource) {
    setFormSource(app);
    setForm(toForm(app));
  }

  if (isLoading) return <LoadingState rows={5} />;
  if (error instanceof ApiError && error.status === 404) return <Alert tone="danger" title="Candidature introuvable" />;
  if (error || !app || !form) return <ErrorState onRetry={() => mutate()} />;

  const refresh = async (updated?: Application) => {
    if (updated) await mutate(updated, { revalidate: false });
    else await mutate();
    await mutateEvents();
  };

  async function saveFields() {
    if (!form) return;
    setSaving(true);
    try {
      const hours = form.estimated_prep_hours ? Number(form.estimated_prep_hours) : null;
      const updated = await api<Application>(`applications/${id}`, {
        method: "PATCH",
        json: {
          deadline_at: localInputToIso(form.deadline_at),
          contact_name: form.contact_name || null,
          contact_email: form.contact_email || null,
          next_action: form.next_action || null,
          next_action_at: localInputToIso(form.next_action_at),
          follow_up_at: localInputToIso(form.follow_up_at),
          estimated_prep_hours: hours,
          notes: form.notes || null,
          response_notes: form.response_notes || null,
          response_received_at: localInputToIso(form.response_received_at),
          ...(app!.submitted_at ? { submitted_at: localInputToIso(form.submitted_at) } : {}),
        },
      });
      await refresh(updated);
      notify(t.common.saved);
    } catch (err) {
      notify(errorMessage(err), "error");
    } finally {
      setSaving(false);
    }
  }

  async function addTask() {
    if (!taskTitle.trim()) return;
    try {
      await api(`applications/${id}/tasks`, { method: "POST", json: { title: taskTitle.trim(), due_at: localInputToIso(taskDue) } });
      setTaskTitle("");
      setTaskDue("");
      await Promise.all([mutateTasks(), refresh()]);
    } catch (err) {
      notify(errorMessage(err), "error");
    }
  }

  async function toggleTask(task: Task) {
    try {
      await api(`tasks/${task.id}`, { method: "PATCH", json: { status: task.status === "done" ? "todo" : "done" } });
      await Promise.all([mutateTasks(), refresh()]);
    } catch (err) {
      notify(errorMessage(err), "error");
    }
  }

  async function linkDocument() {
    if (!docToLink) return;
    try {
      const updated = await api<Application>(`applications/${id}/documents`, { method: "POST", json: { document_id: docToLink } });
      setDocToLink("");
      await refresh(updated);
    } catch (err) {
      notify(errorMessage(err), "error");
    }
  }

  async function unlinkDocument(docId: string) {
    try {
      const updated = await api<Application>(`applications/${id}/documents/${docId}`, { method: "DELETE" });
      await refresh(updated);
    } catch (err) {
      notify(errorMessage(err), "error");
    }
  }

  async function remove() {
    try {
      await api(`applications/${id}`, { method: "DELETE" });
      notify("Candidature retirée du suivi.");
      router.replace("/applications");
    } catch (err) {
      notify(errorMessage(err), "error");
    }
  }

  const set = (key: keyof FormState) => (e: { target: { value: string } }) => setForm({ ...form, [key]: e.target.value });
  const deadline = app.deadline_at ?? app.opportunity.deadline_at;
  const linkedIds = new Set(app.documents.map((d) => d.id));

  return (
    <div className="flex flex-col gap-6">
      <Link href="/applications" className="inline-flex items-center gap-1 text-sm font-bold hover:underline"><ArrowLeft className="size-4" aria-hidden /> Candidatures</Link>
      <header className="flex flex-col gap-3 border-b-2 border-ink pb-6">
        <div className="flex flex-wrap gap-1.5">
          <StatusBadge status={app.status} />
          <DeadlineBadge at={deadline} status={app.deadline_at ? "confirmed" : app.opportunity.deadline_status} tz={tz} />
          <UrgencyBadge urgency={app.urgency} />
          <EligibilityBadge value={app.eligibility} />
        </div>
        <h1 className="text-4xl font-black uppercase leading-[0.95] sm:text-5xl">{app.opportunity.title}</h1>
        <p className="text-lg font-semibold">{app.opportunity.organization}</p>
        <div className="flex flex-wrap gap-2">
          <LinkButton href={`/opportunities/${app.opportunity.id}`}>Analyse de l&apos;offre</LinkButton>
          <LinkButton href={app.opportunity.official_url} external icon={<ExternalLink className="size-4" aria-hidden />}>{t.common.officialSource}</LinkButton>
          <Button variant="danger" onClick={() => setConfirmDelete(true)} icon={<Trash2 className="size-4" aria-hidden />}>Retirer du suivi</Button>
        </div>
      </header>

      <div className="grid gap-6 xl:grid-cols-[1.4fr_1fr]">
        <Card title="Suivi">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5 sm:col-span-2"><StatusControl app={app} onChanged={(a) => refresh(a)} /></div>
            <Field label="Échéance personnelle" hint={app.opportunity.deadline_at ? `Annonce : ${formatDate(app.opportunity.deadline_at, tz, true)} (${label(t.deadlineStatus, app.opportunity.deadline_status)})` : "L'annonce ne publie pas de date."}>
              {(p) => <Input {...p} type="datetime-local" value={form.deadline_at} onChange={set("deadline_at")} />}
            </Field>
            {app.submitted_at && (
              <Field label="Date d'envoi">{(p) => <Input {...p} type="datetime-local" value={form.submitted_at} onChange={set("submitted_at")} />}</Field>
            )}
            <Field label="Prochaine action">{(p) => <Input {...p} value={form.next_action} onChange={set("next_action")} placeholder="ex. Demander une lettre au Pr X" />}</Field>
            <Field label="Date de la prochaine action">{(p) => <Input {...p} type="datetime-local" value={form.next_action_at} onChange={set("next_action_at")} />}</Field>
            <Field label="Date de relance">{(p) => <Input {...p} type="datetime-local" value={form.follow_up_at} onChange={set("follow_up_at")} />}</Field>
            <Field label="Temps de préparation estimé (h)">{(p) => <Input {...p} type="number" min={0} max={500} value={form.estimated_prep_hours} onChange={set("estimated_prep_hours")} />}</Field>
            <Field label="Contact">{(p) => <Input {...p} value={form.contact_name} onChange={set("contact_name")} />}</Field>
            <Field label="E-mail du contact">{(p) => <Input {...p} type="email" value={form.contact_email} onChange={set("contact_email")} />}</Field>
            <Field label="Notes" className="sm:col-span-2">{(p) => <Textarea {...p} rows={5} value={form.notes} onChange={set("notes")} />}</Field>
            <Field label="Réponses reçues" className="sm:col-span-2">{(p) => <Textarea {...p} rows={3} value={form.response_notes} onChange={set("response_notes")} />}</Field>
            <Field label="Date de la réponse">{(p) => <Input {...p} type="datetime-local" value={form.response_received_at} onChange={set("response_received_at")} />}</Field>
          </div>
          <Button className="mt-5" onClick={saveFields} loading={saving}>{t.common.save}</Button>
        </Card>

        <div className="flex flex-col gap-6">
          <Card title="Priorité" description="Indicateur explicable, recalculé à chaque consultation.">
            {app.urgency ? (
              <>
                <div className="mb-3 flex items-center gap-3"><UrgencyBadge urgency={app.urgency} /><span className="text-sm font-bold">{app.urgency.score}/100</span></div>
                <ul className="flex list-disc flex-col gap-1 pl-5 text-sm">{app.urgency.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
              </>
            ) : <p className="text-sm text-ink-soft">Candidature envoyée ou clôturée : plus de priorité calculée.</p>}
            <div className="mt-4 border-t-2 border-ink pt-3"><ScoreMeter score={app.score} /></div>
          </Card>

          <Card title="Documents">
            {app.opportunity.required_documents.length > 0 && (
              <p className="mb-3 text-sm"><strong>Exigés :</strong> {app.opportunity.required_documents.join(", ")}</p>
            )}
            <ul className="mb-3 flex flex-col gap-2">
              {app.documents.length === 0 && <li className="text-sm text-ink-soft">Aucun document associé.</li>}
              {app.documents.map((d) => (
                <li key={d.id} className="flex items-center justify-between gap-2 border-2 border-ink px-2 py-1.5 text-sm">
                  <span><strong>{d.title}</strong> <Badge tone="outline">{label(t.documentType, d.doc_type)}</Badge> v{d.version}</span>
                  <Button size="sm" variant="ghost" onClick={() => unlinkDocument(d.id)} aria-label={`Retirer ${d.title}`}><Unlink className="size-4" aria-hidden /></Button>
                </li>
              ))}
            </ul>
            <div className="flex gap-2">
              <label htmlFor="link-doc" className="sr-only">Document à associer</label>
              <Select id="link-doc" value={docToLink} onChange={(e) => setDocToLink(e.target.value)}>
                <option value="">Choisir un document…</option>
                {(documents ?? []).filter((d) => !linkedIds.has(d.id)).map((d) => (
                  <option key={d.id} value={d.id}>{d.title} ({label(t.documentType, d.doc_type)} v{d.version})</option>
                ))}
              </Select>
              <Button onClick={linkDocument} disabled={!docToLink} icon={<Link2 className="size-4" aria-hidden />}>Associer</Button>
            </div>
            {documents && documents.length === 0 && <p className="mt-2 text-xs"><Link href="/documents" className="underline">Téléversez d&apos;abord vos documents.</Link></p>}
          </Card>

          <Card title="Tâches">
            <ul className="mb-3 flex flex-col gap-2">
              {(tasks ?? []).length === 0 && <li className="text-sm text-ink-soft">Aucune tâche.</li>}
              {(tasks ?? []).map((task) => (
                <li key={task.id} className={`flex items-center gap-2 border-2 px-2 py-1.5 text-sm ${task.overdue ? "border-danger bg-danger-soft" : "border-ink"}`}>
                  <button type="button" onClick={() => toggleTask(task)} aria-pressed={task.status === "done"} aria-label={task.status === "done" ? `Rouvrir ${task.title}` : `Terminer ${task.title}`}
                    className={`grid size-6 shrink-0 place-items-center border-2 border-ink ${task.status === "done" ? "bg-accent" : "bg-paper"}`}>
                    {task.status === "done" && <Check className="size-4" aria-hidden />}
                  </button>
                  <span className={task.status === "done" ? "line-through" : "font-semibold"}>{task.title}</span>
                  {task.due_at && <span className="ml-auto shrink-0 text-xs">{formatDate(task.due_at, tz, true)}</span>}
                </li>
              ))}
            </ul>
            <div className="flex flex-col gap-2 sm:flex-row">
              <label htmlFor="task-title" className="sr-only">Nouvelle tâche</label>
              <Input id="task-title" placeholder="Nouvelle tâche…" value={taskTitle} onChange={(e) => setTaskTitle(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addTask()} />
              <label htmlFor="task-due" className="sr-only">Échéance de la tâche</label>
              <Input id="task-due" type="datetime-local" value={taskDue} onChange={(e) => setTaskDue(e.target.value)} className="sm:w-56" />
              <Button onClick={addTask} icon={<Plus className="size-4" aria-hidden />}>{t.common.add}</Button>
            </div>
          </Card>

          <Card title="Historique">
            <ol className="flex flex-col gap-2 border-l-2 border-ink pl-4 text-sm">
              {(events ?? []).map((e) => (
                <li key={e.id}>
                  <p className="font-bold">{EVENT_LABELS[e.event_type] ?? e.event_type}
                    {e.to_status && <> : {e.from_status ? `${label(t.applicationStatus, e.from_status)} → ` : ""}{label(t.applicationStatus, e.to_status)}</>}
                  </p>
                  <p className="text-xs text-ink-soft">{formatDate(e.created_at, tz, true)}{Array.isArray(e.details.fields) ? ` · ${(e.details.fields as string[]).join(", ")}` : ""}{typeof e.details.title === "string" ? ` · ${e.details.title}` : ""}</p>
                </li>
              ))}
            </ol>
          </Card>
        </div>
      </div>

      <AssistPanel opportunityId={app.opportunity.id} applicationId={app.id} />

      <Modal open={confirmDelete} onClose={() => setConfirmDelete(false)} title="Retirer du suivi ?"
        description="La candidature, ses tâches et son historique seront supprimés. Les documents restent dans votre espace."
        footer={<><Button variant="secondary" onClick={() => setConfirmDelete(false)}>{t.common.cancel}</Button><Button variant="danger" onClick={remove}>{t.common.delete}</Button></>} />
    </div>
  );
}
