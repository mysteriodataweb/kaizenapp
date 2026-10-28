"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { type ReactNode, useState } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox, Field, FormError, Input, Select, Textarea } from "@/components/ui/form";
import { TagInput } from "@/components/ui/tag-input";
import { t } from "@/i18n";
import { errorMessage } from "@/lib/api";
import { COMMON_COUNTRIES, countryName, dayKey, parseCountryInput } from "@/lib/format";
import type { ImportDraft, OpportunityDetail } from "@/lib/types";

export const offerSchema = z.object({
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
  description: z.string().max(30000),
  follow: z.boolean(),
});
export type OfferValues = z.infer<typeof offerSchema>;

const STUDY_LEVELS = ["bachelor", "master", "doctorate", "secondary", "other"] as const;

const EMPTY: Omit<OfferValues, "official_url" | "type"> = {
  title: "", organization: "", location: "", countries: [], remote: "unknown", deadline_date: "", deadline_confirmed: false,
  duration_months: "", funding_type: "unknown", funding_amount: "", stipend: "", study_levels: [], fields: [],
  required_documents: [], eligibility_criteria: "", description: "", follow: true,
};

const remoteValue = (r: boolean | null): OfferValues["remote"] => (r === true ? "yes" : r === false ? "no" : "unknown");

export function draftToValues(d: ImportDraft): Partial<OfferValues> {
  return {
    ...EMPTY,
    official_url: d.official_url,
    type: d.type ?? undefined,
    title: d.title ?? "",
    organization: d.organization ?? "",
    location: d.location ?? "",
    countries: d.countries,
    remote: remoteValue(d.remote),
    deadline_date: d.deadline_date ?? "",
    duration_months: d.duration_months ? String(d.duration_months) : "",
    stipend: d.stipend ?? "",
    fields: d.fields,
    required_documents: d.required_documents,
    eligibility_criteria: d.eligibility_criteria ?? "",
    description: d.description ?? "",
  };
}

export function detailToValues(o: OpportunityDetail, tz: string): Partial<OfferValues> {
  return {
    ...EMPTY,
    official_url: o.official_url,
    type: o.type,
    title: o.title,
    organization: o.organization,
    location: o.location ?? "",
    countries: o.countries,
    remote: remoteValue(o.remote),
    deadline_date: o.deadline_at ? dayKey(new Date(o.deadline_at), tz) : "",
    deadline_confirmed: o.deadline_status === "confirmed",
    duration_months: o.duration_months ? String(o.duration_months) : "",
    funding_type: o.funding_type,
    funding_amount: o.funding_amount ?? "",
    stipend: o.stipend ?? "",
    study_levels: o.study_levels,
    fields: o.fields,
    required_documents: o.required_documents,
    eligibility_criteria: o.eligibility_criteria ?? "",
    description: o.description ?? "",
    follow: false,
  };
}

/** Champs envoyés à l'API (sans l'option de suivi, propre à l'ajout). */
export function toOfferPayload(v: OfferValues) {
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
  };
}

interface OfferFormProps {
  initial: Partial<OfferValues>;
  title: string;
  intro?: ReactNode;
  submitLabel: string;
  showFollow?: boolean;
  onSubmit: (values: OfferValues) => Promise<void>;
  onCancel: () => void;
}

export function OfferForm({ initial, title, intro, submitLabel, showFollow = false, onSubmit, onCancel }: OfferFormProps) {
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, control, formState } = useForm<OfferValues>({ resolver: zodResolver(offerSchema), defaultValues: initial });
  const deadline = useWatch({ control, name: "deadline_date" });
  const errors = formState.errors;

  async function submit(values: OfferValues) {
    setError(null);
    try {
      await onSubmit(values);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <form onSubmit={handleSubmit(submit)} noValidate className="mt-6 flex flex-col gap-6">
      {intro}
      <Card title={title}>
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
          {showFollow && (
            <Checkbox label="Ajouter à ma liste « À postuler »" description="Suivie dans vos candidatures avec le statut « À explorer »." {...register("follow")} />
          )}
          <p className="text-sm text-ink-soft">Offre personnelle : visible de vous seul. Rien n&apos;est envoyé à l&apos;organisme ni à LinkedIn.</p>
          <FormError message={error} />
          <div className="flex flex-wrap gap-2">
            <Button type="submit" loading={formState.isSubmitting}>{submitLabel}</Button>
            <Button type="button" variant="secondary" onClick={onCancel}>Annuler</Button>
          </div>
        </div>
      </Card>
    </form>
  );
}
