"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { Button, LinkButton } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Alert } from "@/components/ui/feedback";
import { Checkbox, Field, FormError, Input, Select, Textarea } from "@/components/ui/form";
import { PageHeader } from "@/components/ui/page-header";
import { TagInput } from "@/components/ui/tag-input";
import { useToast } from "@/components/ui/toast";
import { t } from "@/i18n";
import { api, errorMessage } from "@/lib/api";
import { COMMON_COUNTRIES, countryName, parseCountryInput } from "@/lib/format";
import type { ImportPreview, ImportResult } from "@/lib/types";

const importSchema = z.object({
  official_url: z.string().trim().regex(/^https?:\/\/\S+$/i, "Lien http(s) invalide."),
  type: z.enum(["internship", "masters_scholarship"], { message: "Choisissez le type." }),
  title: z.string().trim().min(3, "3 caractères minimum.").max(400),
  organization: z.string().trim().min(1, "Organisme requis.").max(300),
  location: z.string().trim().max(300),
  countries: z.array(z.string()),
  remote: z.enum(["unknown", "yes", "no"]),
  deadline_date: z.string(),
  deadline_confirmed: z.boolean(),
  duration_months: z.string().regex(/^(\d{1,2})?$/, "Nombre de mois (0 à 60)."),
  funding_type: z.enum(["unknown", "full", "partial", "none"]),
  funding_amount: z.string().trim().max(200),
  stipend: z.string().trim().max(200),
  study_levels: z.array(z.string()),
  fields: z.array(z.string()),
  required_documents: z.array(z.string()),
  eligibility_criteria: z.string().max(10000),
  description: z.string().max(20000),
  follow: z.boolean(),
});
export type ImportValues = z.infer<typeof importSchema>;

const STUDY_LEVELS = ["bachelor", "master", "doctorate", "secondary", "other"] as const;

export function toImportPayload(v: ImportValues) {
  return {
    official_url: v.official_url.trim(),
    type: v.type,
    title: v.title.trim(),
    organization: v.organization.trim(),
    location: v.location.trim() || null,
    countries: v.countries,
    remote: v.remote === "yes" ? true : v.remote === "no" ? false : null,
    deadline_date: v.deadline_date || null,
    deadline_confirmed: Boolean(v.deadline_date) && v.deadline_confirmed,
    duration_months: v.duration_months ? Number(v.duration_months) : null,
    funding_type: v.funding_type,
    funding_amount: v.funding_amount || null,
    stipend: v.stipend || null,
    study_levels: v.study_levels,
    fields: v.fields,
    required_documents: v.required_documents,
    eligibility_criteria: v.eligibility_criteria.trim() || null,
    description: v.description.trim() || null,
    follow: v.follow,
  };
}

export function ImportView() {
  const [url, setUrl] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);

  async function analyze(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setPreview(null);
    setAnalyzing(true);
    try {
      setPreview(await api<ImportPreview>("opportunities/import/preview", { method: "POST", json: { url: url.trim() } }));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setAnalyzing(false);
    }
  }

  return (
    <>
      <PageHeader eyebrow="Catalogue" title="Ajouter une offre"
        description="Collez le lien d'une offre de stage ou d'un appel à bourses. La page est lue si le site l'autorise, un brouillon est pré-rempli, vous le relisez, puis l'offre rejoint le catalogue avec son score de compatibilité." />
      <Card title="1. Lien de l'offre">
        <form onSubmit={analyze} noValidate className="flex flex-col gap-3 md:flex-row md:items-end">
          <Field label="Adresse de la page de l'offre" className="flex-1" hint="Page officielle de préférence (site de l'entreprise, de l'université ou du programme).">
            {(p) => <Input {...p} type="url" inputMode="url" placeholder="https://…" value={url} onChange={(e) => setUrl(e.target.value)} />}
          </Field>
          <Button type="submit" loading={analyzing} disabled={!/^https?:\/\/\S+$/i.test(url.trim())} icon={<Search className="size-4" aria-hidden />}>
            Analyser le lien
          </Button>
        </form>
        <div className="mt-3"><FormError message={error} /></div>
      </Card>

      {preview?.existing_opportunity_id ? (
        <Alert tone="info" className="mt-6" title="Cette offre est déjà dans le catalogue"
          action={<LinkButton href={`/opportunities/${preview.existing_opportunity_id}`} size="sm">Voir l&apos;offre</LinkButton>}>
          Inutile de l&apos;ajouter à nouveau : ouvrez-la pour la suivre ou la mettre en favori.
        </Alert>
      ) : preview ? (
        <ImportForm key={preview.url} preview={preview} onCancel={() => setPreview(null)} />
      ) : null}
    </>
  );
}

function ImportForm({ preview, onCancel }: { preview: ImportPreview; onCancel: () => void }) {
  const router = useRouter();
  const { notify } = useToast();
  const [error, setError] = useState<string | null>(null);
  const d = preview.draft;
  const { register, handleSubmit, control, formState } = useForm<ImportValues>({
    resolver: zodResolver(importSchema),
    defaultValues: {
      official_url: d.official_url,
      type: d.type ?? undefined,
      title: d.title ?? "",
      organization: d.organization ?? "",
      location: d.location ?? "",
      countries: d.countries,
      remote: d.remote === true ? "yes" : d.remote === false ? "no" : "unknown",
      deadline_date: d.deadline_date ?? "",
      deadline_confirmed: false,
      duration_months: "",
      funding_type: "unknown",
      funding_amount: "",
      stipend: d.stipend ?? "",
      study_levels: [],
      fields: d.fields,
      required_documents: [],
      eligibility_criteria: "",
      description: d.description ?? "",
      follow: true,
    },
  });
  const deadline = useWatch({ control, name: "deadline_date" });
  const errors = formState.errors;

  async function save(values: ImportValues) {
    setError(null);
    try {
      const res = await api<ImportResult>("opportunities/import", { method: "POST", json: toImportPayload(values) });
      notify(res.message);
      router.push(`/opportunities/${res.opportunity_id}`);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <form onSubmit={handleSubmit(save)} noValidate className="mt-6 flex flex-col gap-6">
      <Alert tone={preview.fetched ? "info" : "warning"} title={preview.fetched ? "Brouillon pré-rempli : relisez chaque champ" : "Lecture automatique impossible"}>
        <ul className="list-disc pl-5">
          {preview.notes.map((note) => <li key={note}>{note}</li>)}
        </ul>
      </Alert>

      <Card title="2. Vérifier et compléter">
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Type" error={errors.type?.message} required>{(p) => (
            <Select {...p} {...register("type")}>
              <option value="">Choisir…</option>
              <option value="internship">{t.opportunityType.internship}</option>
              <option value="masters_scholarship">{t.opportunityType.masters_scholarship}</option>
            </Select>
          )}</Field>
          <Field label="Organisme" error={errors.organization?.message} required>{(p) => <Input {...p} {...register("organization")} maxLength={300} />}</Field>
          <Field label="Intitulé" className="md:col-span-2" error={errors.title?.message} required>{(p) => <Input {...p} {...register("title")} maxLength={400} />}</Field>
          <Field label="Lien officiel" className="md:col-span-2" error={errors.official_url?.message} required>{(p) => <Input {...p} type="url" {...register("official_url")} />}</Field>
          <Field label="Lieu" hint="Ville, région… tel que publié.">{(p) => <Input {...p} {...register("location")} maxLength={300} />}</Field>
          <Field label="Télétravail">{(p) => (
            <Select {...p} {...register("remote")}>
              <option value="unknown">Non précisé</option>
              <option value="yes">Oui</option>
              <option value="no">Non</option>
            </Select>
          )}</Field>
          <div className="md:col-span-2">
            <Controller control={control} name="countries" render={({ field }) => (
              <TagInput label="Pays" hint="Code ISO (FR, SN…) ou nom du pays." value={field.value} onChange={field.onChange}
                normalize={parseCountryInput} renderTag={countryName} suggestions={COMMON_COUNTRIES.map(countryName)} max={30} />
            )} />
          </div>
          <div className="flex flex-col gap-2">
            <Field label="Date limite" hint="Laissez vide si aucune date n'est publiée.">{(p) => <Input {...p} type="date" {...register("deadline_date")} />}</Field>
            <Checkbox label="J'ai vérifié cette date sur la page officielle" disabled={!deadline} {...register("deadline_confirmed")} />
          </div>
          <Field label="Durée (mois)" error={errors.duration_months?.message}>{(p) => <Input {...p} inputMode="numeric" {...register("duration_months")} />}</Field>
          <Field label="Financement">{(p) => (
            <Select {...p} {...register("funding_type")}>
              {(["unknown", "full", "partial", "none"] as const).map((f) => <option key={f} value={f}>{t.funding[f]}</option>)}
            </Select>
          )}</Field>
          <Field label="Montant du financement" hint="Ex. 1 200 €/mois, frais de scolarité couverts…">{(p) => <Input {...p} {...register("funding_amount")} maxLength={200} />}</Field>
          <Field label="Gratification / salaire">{(p) => <Input {...p} {...register("stipend")} maxLength={200} />}</Field>
          <fieldset className="md:col-span-2">
            <legend className="mb-2 text-sm font-bold">Niveau d&apos;études requis</legend>
            <div className="flex flex-wrap gap-4">
              {STUDY_LEVELS.map((level) => (
                <Checkbox key={level} label={t.studyLevel[level]} value={level} {...register("study_levels")} />
              ))}
            </div>
          </fieldset>
          <Controller control={control} name="fields" render={({ field }) => (
            <TagInput label="Domaines" value={field.value} onChange={field.onChange} placeholder="data, énergie…" max={20} />
          )} />
          <Controller control={control} name="required_documents" render={({ field }) => (
            <TagInput label="Documents demandés" value={field.value} onChange={field.onChange} placeholder="CV, lettre de motivation…" max={20} />
          )} />
          <Field label="Critères d'éligibilité" className="md:col-span-2" hint="Recopiez les conditions publiées (nationalités, diplôme, langues…).">{(p) => <Textarea {...p} {...register("eligibility_criteria")} />}</Field>
          <Field label="Description" className="md:col-span-2">{(p) => <Textarea {...p} className="min-h-48" {...register("description")} />}</Field>
        </div>
      </Card>

      <Card>
        <div className="flex flex-col gap-4">
          <Checkbox label="Suivre cette offre" description="Ajoutée à vos candidatures avec le statut « À explorer »." {...register("follow")} />
          <p className="text-sm text-ink-soft">
            L&apos;offre rejoint le catalogue commun avec la mention « Ajout manuel », visible par les autres membres. Rien n&apos;est envoyé à l&apos;organisme.
          </p>
          <FormError message={error} />
          <div className="flex flex-wrap gap-2">
            <Button type="submit" loading={formState.isSubmitting}>Ajouter au catalogue</Button>
            <Button type="button" variant="secondary" onClick={onCancel}>Annuler</Button>
          </div>
        </div>
      </Card>
    </form>
  );
}
