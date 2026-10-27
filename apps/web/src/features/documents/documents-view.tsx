"use client";

import { Download, FilePlus2, Pencil, RefreshCcw, Trash2 } from "lucide-react";
import { type FormEvent, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { type Column, DataTable } from "@/components/ui/data-table";
import { Alert, EmptyState, ErrorState, LoadingState } from "@/components/ui/feedback";
import { Field, FormError, Input, Select, Textarea } from "@/components/ui/form";
import { Modal } from "@/components/ui/modal";
import { PageHeader } from "@/components/ui/page-header";
import { useToast } from "@/components/ui/toast";
import { useUser } from "@/features/shared/user-context";
import { label, t } from "@/i18n";
import { api, errorMessage } from "@/lib/api";
import { formatBytes, formatDate } from "@/lib/format";
import type { DocumentItem } from "@/lib/types";
import { useApi } from "@/lib/use-api";

const MAX_MB = 4;
const ACCEPT = ".pdf,.docx,.png,.jpg,.jpeg,.txt,application/pdf";

export function DocumentsView() {
  const user = useUser();
  const { notify } = useToast();
  const [filter, setFilter] = useState("");
  const { data, error, isLoading, mutate } = useApi<DocumentItem[]>(`documents${filter ? `?doc_type=${filter}` : ""}`);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [replaces, setReplaces] = useState<DocumentItem | null>(null);
  const [editing, setEditing] = useState<DocumentItem | null>(null);
  const [deleting, setDeleting] = useState<DocumentItem | null>(null);

  async function download(doc: DocumentItem) {
    try {
      const link = await api<{ mode: string; url: string }>(`documents/${doc.id}/download`);
      // URL signée à durée limitée (S3) ou flux authentifié via la passerelle.
      window.location.assign(link.mode === "redirect" ? link.url : `/api/backend${link.url}`);
    } catch (err) {
      notify(errorMessage(err), "error");
    }
  }

  async function remove() {
    if (!deleting) return;
    try {
      await api(`documents/${deleting.id}`, { method: "DELETE" });
      notify("Document supprimé.");
      setDeleting(null);
      await mutate();
    } catch (err) {
      notify(errorMessage(err), "error");
    }
  }

  const columns: Column<DocumentItem>[] = [
    { key: "title", header: "Document", cell: (d) => <div><p className="font-bold">{d.title}</p><p className="text-xs text-ink-soft">{d.original_filename}</p></div> },
    { key: "type", header: "Type", cell: (d) => <Badge tone="outline">{label(t.documentType, d.doc_type)}</Badge> },
    { key: "version", header: "Version", cell: (d) => `v${d.version}` },
    { key: "date", header: "Ajouté le", cell: (d) => formatDate(d.created_at, user.timezone) },
    { key: "size", header: "Taille", cell: (d) => formatBytes(d.size_bytes), mobile: false },
    { key: "apps", header: "Candidatures", cell: (d) => d.application_ids.length },
    { key: "notes", header: "Notes", cell: (d) => <span className="line-clamp-2 text-ink-soft">{d.notes ?? "—"}</span>, mobile: false },
    { key: "actions", header: "Actions", cell: (d) => (
      <div className="flex flex-wrap gap-1">
        <Button size="sm" variant="secondary" onClick={() => download(d)} aria-label={`Télécharger ${d.title}`}><Download className="size-4" aria-hidden /></Button>
        <Button size="sm" variant="secondary" onClick={() => setEditing(d)} aria-label={`Modifier ${d.title}`}><Pencil className="size-4" aria-hidden /></Button>
        <Button size="sm" variant="secondary" onClick={() => { setReplaces(d); setUploadOpen(true); }} aria-label={`Nouvelle version de ${d.title}`}><RefreshCcw className="size-4" aria-hidden /></Button>
        <Button size="sm" variant="danger" onClick={() => setDeleting(d)} aria-label={`Supprimer ${d.title}`}><Trash2 className="size-4" aria-hidden /></Button>
      </div>
    ) },
  ];

  return (
    <>
      <PageHeader eyebrow="Espace privé" title={t.nav.documents}
        description={`Fichiers privés (PDF, DOCX, PNG, JPEG, texte — ${MAX_MB} Mo max). Le type réel est vérifié côté serveur.`}
        actions={<Button onClick={() => { setReplaces(null); setUploadOpen(true); }} icon={<FilePlus2 className="size-4" aria-hidden />}>Téléverser</Button>} />
      <div className="mb-4 flex items-center gap-2">
        <label htmlFor="doc-filter" className="text-sm font-bold">Type</label>
        <Select id="doc-filter" value={filter} onChange={(e) => setFilter(e.target.value)} className="w-64">
          <option value="">Tous</option>
          {Object.entries(t.documentType).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
      </div>
      {isLoading ? <LoadingState /> : error ? <ErrorState onRetry={() => mutate()} /> : (
        <DataTable rows={data ?? []} columns={columns} rowKey={(d) => d.id} caption="Documents"
          empty={<EmptyState title="Aucun document" description="Ajoutez CV, relevés, lettres… puis associez-les à vos candidatures." />} />
      )}
      <UploadModal open={uploadOpen} replaces={replaces} onClose={() => setUploadOpen(false)} onDone={() => { setUploadOpen(false); void mutate(); }} />
      {editing && <EditModal doc={editing} onClose={() => setEditing(null)} onDone={() => { setEditing(null); void mutate(); }} />}
      <Modal open={deleting !== null} onClose={() => setDeleting(null)} title="Supprimer le document ?"
        description="Le fichier sera définitivement supprimé du stockage et retiré des candidatures associées."
        footer={<><Button variant="secondary" onClick={() => setDeleting(null)}>{t.common.cancel}</Button><Button variant="danger" onClick={remove}>{t.common.delete}</Button></>}>
        <p className="font-semibold">{deleting?.title}</p>
      </Modal>
    </>
  );
}

function UploadModal({ open, replaces, onClose, onDone }: { open: boolean; replaces: DocumentItem | null; onClose: () => void; onDone: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { notify } = useToast();

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    const formEl = e.currentTarget;
    const file = fileRef.current?.files?.[0];
    if (!file) return setError("Choisissez un fichier.");
    if (file.size > MAX_MB * 1024 * 1024) return setError(`Fichier trop volumineux (max ${MAX_MB} Mo).`);
    const body = new FormData(formEl);
    if (replaces) body.set("replaces", replaces.id);
    setLoading(true);
    try {
      await api("documents", { method: "POST", body });
      notify(replaces ? "Nouvelle version enregistrée." : "Document ajouté.");
      formEl.reset();
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={replaces ? `Nouvelle version : ${replaces.title}` : "Téléverser un document"}>
      <form onSubmit={submit} className="flex flex-col gap-4" encType="multipart/form-data">
        <Field label="Fichier" required>{(p) => <Input {...p} ref={fileRef} name="file" type="file" accept={ACCEPT} className="h-auto py-2" />}</Field>
        <Field label="Type" required>{(p) => (
          <Select {...p} name="doc_type" defaultValue={replaces?.doc_type ?? "cv"}>
            {Object.entries(t.documentType).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
        )}</Field>
        <Field label="Titre">{(p) => <Input {...p} name="title" defaultValue={replaces?.title ?? ""} maxLength={200} />}</Field>
        <Field label="Notes">{(p) => <Textarea {...p} name="notes" rows={2} maxLength={5000} />}</Field>
        <FormError message={error} />
        <Alert tone="info">Ne téléversez que vos propres documents. Ils restent privés et ne sont jamais partagés.</Alert>
        <Button type="submit" loading={loading}>Téléverser</Button>
      </form>
    </Modal>
  );
}

function EditModal({ doc, onClose, onDone }: { doc: DocumentItem; onClose: () => void; onDone: () => void }) {
  const [title, setTitle] = useState(doc.title);
  const [docType, setDocType] = useState(doc.doc_type);
  const [notes, setNotes] = useState(doc.notes ?? "");
  const [error, setError] = useState<string | null>(null);
  async function save() {
    try {
      await api(`documents/${doc.id}`, { method: "PATCH", json: { title, doc_type: docType, notes: notes || null } });
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    }
  }
  return (
    <Modal open onClose={onClose} title="Modifier le document" footer={<><Button variant="secondary" onClick={onClose}>{t.common.cancel}</Button><Button onClick={save}>{t.common.save}</Button></>}>
      <Field label="Titre">{(p) => <Input {...p} value={title} onChange={(e) => setTitle(e.target.value)} />}</Field>
      <Field label="Type">{(p) => (
        <Select {...p} value={docType} onChange={(e) => setDocType(e.target.value)}>
          {Object.entries(t.documentType).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
      )}</Field>
      <Field label="Notes">{(p) => <Textarea {...p} value={notes} onChange={(e) => setNotes(e.target.value)} />}</Field>
      <FormError message={error} />
    </Modal>
  );
}

