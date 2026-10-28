"use client";

import { ListPlus, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { Button, LinkButton } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Alert } from "@/components/ui/feedback";
import { Field, FormError, Input, Select, Textarea } from "@/components/ui/form";
import { PageHeader } from "@/components/ui/page-header";
import { Segmented } from "@/components/ui/segmented";
import { useToast } from "@/components/ui/toast";
import { t } from "@/i18n";
import { api, errorMessage } from "@/lib/api";
import type { ImportPreview, ImportResult, OpportunityType, QuickImportResult } from "@/lib/types";
import { draftToValues, OfferForm, type OfferValues, toOfferPayload } from "./offer-form";

const URL_RE = /^https?:\/\/\S+$/i;
const LINKEDIN_RE = /^https?:\/\/([\w-]+\.)?linkedin\.com\//i;
export const MAX_QUICK_LINKS = 50;

/** Liens http(s) d'un texte collé (un par ligne, ou séparés par des espaces), sans doublon. */
export function extractLinks(text: string): string[] {
  return [...new Set(text.split(/\s+/).map((s) => s.trim()).filter((s) => URL_RE.test(s)))];
}

type Mode = "quick" | "detailed";

export function ImportView() {
  const [mode, setMode] = useState<Mode>("quick");
  return (
    <>
      <PageHeader eyebrow="Mes offres" title="Enregistrer des offres"
        description="Gardez de côté les offres trouvées (LinkedIn ou ailleurs) pour postuler plus tard, une par une. Elles ne sont visibles que par vous."
        actions={<LinkButton href="/queue" variant="secondary">Ma liste « À postuler »</LinkButton>} />
      <Segmented label="Mode d'ajout" value={mode} onChange={setMode}
        options={[{ value: "quick", label: "Plusieurs liens" }, { value: "detailed", label: "Une offre détaillée" }]} />
      <div className="mt-4">{mode === "quick" ? <QuickSave /> : <DetailedImport />}</div>
    </>
  );
}

function QuickSave() {
  const [text, setText] = useState("");
  const [type, setType] = useState<OpportunityType>("internship");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<QuickImportResult | null>(null);
  const links = extractLinks(text);

  async function save(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSaving(true);
    try {
      setResult(await api<QuickImportResult>("opportunities/import/quick", { method: "POST", json: { urls: links, type } }));
      setText("");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <Card title="Coller des liens">
        <form onSubmit={save} noValidate className="flex flex-col gap-4">
          <Field label="Liens des offres" hint={`Un par ligne, ${MAX_QUICK_LINKS} au plus. Aucune page n'est lue : chaque offre est enregistrée avec ce que contient son lien, puis ajoutée à « À postuler ». Vous compléterez les détails plus tard si besoin.`}>
            {(p) => <Textarea {...p} className="min-h-40 font-mono text-sm" placeholder={"https://www.linkedin.com/jobs/view/…\nhttps://www.linkedin.com/jobs/view/…"} value={text} onChange={(e) => setText(e.target.value)} />}
          </Field>
          <Field label="Type des offres">{(p) => (
            <Select {...p} value={type} onChange={(e) => setType(e.target.value as OpportunityType)}>
              <option value="internship">{t.opportunityType.internship}</option>
              <option value="masters_scholarship">{t.opportunityType.masters_scholarship}</option>
            </Select>
          )}</Field>
          <FormError message={error} />
          {links.length > MAX_QUICK_LINKS && <FormError message={`${links.length} liens : ${MAX_QUICK_LINKS} au plus par envoi.`} />}
          <Button type="submit" className="self-start" loading={saving} disabled={links.length === 0 || links.length > MAX_QUICK_LINKS}
            icon={<ListPlus className="size-4" aria-hidden />}>
            {links.length > 1 ? `Enregistrer ${links.length} liens` : "Enregistrer le lien"}
          </Button>
        </form>
      </Card>
      {result && (
        <Alert tone={result.errors ? "warning" : "success"}
          title={`${result.created} enregistrée(s) · ${result.already_saved} déjà présente(s) · ${result.errors} erreur(s)`}
          action={<LinkButton href="/queue" size="sm">Commencer à postuler</LinkButton>}>
          <ul className="mt-2 flex flex-col gap-1 text-sm">
            {result.items.map((item) => (
              <li key={item.url} className="break-all">
                {item.error ? <span className="font-bold text-danger">✗ {item.error}</span> : <span className="font-bold">{item.created ? "✓" : "="} {item.title}</span>}
                <span className="block text-xs text-ink-soft">{item.url}</span>
              </li>
            ))}
          </ul>
        </Alert>
      )}
    </div>
  );
}

function DetailedImport() {
  const router = useRouter();
  const { notify } = useToast();
  const [url, setUrl] = useState("");
  const [text, setText] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const isLinkedIn = LINKEDIN_RE.test(url.trim());

  async function analyze(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setPreview(null);
    setAnalyzing(true);
    try {
      const json = { url: url.trim(), text: text.trim() || null };
      setPreview(await api<ImportPreview>("opportunities/import/preview", { method: "POST", json }));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setAnalyzing(false);
    }
  }

  async function save(values: OfferValues) {
    const res = await api<ImportResult>("opportunities/import", { method: "POST", json: { ...toOfferPayload(values), follow: values.follow } });
    notify(res.message);
    router.push(`/opportunities/${res.opportunity_id}`);
  }

  return (
    <>
      <Card title="1. Lien et texte de l'offre">
        <form onSubmit={analyze} noValidate className="flex flex-col gap-4">
          <Field label="Adresse de la page de l'offre" hint="LinkedIn, site carrières, page d'un programme de bourses…">
            {(p) => <Input {...p} type="url" inputMode="url" placeholder="https://…" value={url} onChange={(e) => setUrl(e.target.value)} />}
          </Field>
          <Field label="Texte de l'offre (facultatif)"
            hint={isLinkedIn
              ? "LinkedIn ne peut pas être lu automatiquement : ouvrez l'offre, copiez sa description (titre, entreprise, lieu, missions, profil) et collez-la ici."
              : "Utile si la page ne peut pas être lue automatiquement. Avec l'assistant IA configuré, l'intitulé, l'entreprise, le lieu, la date et les critères sont remplis à partir de ce texte."}>
            {(p) => <Textarea {...p} className="min-h-32" maxLength={30000} value={text} onChange={(e) => setText(e.target.value)} />}
          </Field>
          <Button type="submit" className="self-start" loading={analyzing} disabled={!URL_RE.test(url.trim())} icon={<Search className="size-4" aria-hidden />}>
            Analyser
          </Button>
        </form>
        <div className="mt-3"><FormError message={error} /></div>
      </Card>

      {preview?.existing_opportunity_id ? (
        <Alert tone="info" className="mt-6" title="Cette offre est déjà enregistrée"
          action={<LinkButton href={`/opportunities/${preview.existing_opportunity_id}`} size="sm">Voir l&apos;offre</LinkButton>}>
          Inutile de l&apos;ajouter à nouveau : ouvrez-la pour la suivre ou la compléter.
        </Alert>
      ) : preview ? (
        <OfferForm key={`${preview.url}:${preview.method}`} initial={draftToValues(preview.draft)} title="2. Vérifier et compléter" submitLabel="Enregistrer l'offre" showFollow
          onSubmit={save} onCancel={() => setPreview(null)}
          intro={
            <Alert tone={preview.fetched || preview.ai_used ? "info" : "warning"}
              title={preview.ai_used ? "Brouillon rempli par l'IA : relisez chaque champ" : preview.fetched ? "Brouillon pré-rempli : relisez chaque champ" : "Lecture automatique impossible"}>
              <ul className="list-disc pl-5">
                {preview.notes.map((note) => <li key={note}>{note}</li>)}
              </ul>
            </Alert>
          } />
      ) : null}
    </>
  );
}
