"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Controller, type Resolver, useFieldArray, useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ErrorState, LoadingState } from "@/components/ui/feedback";
import { Checkbox, Field, FormError, Input, Select, Textarea } from "@/components/ui/form";
import { PageHeader } from "@/components/ui/page-header";
import { ProgressBar } from "@/components/ui/progress";
import { TagInput } from "@/components/ui/tag-input";
import { useToast } from "@/components/ui/toast";
import { t } from "@/i18n";
import { api, errorMessage } from "@/lib/api";
import { CEFR_LEVELS, COMMON_COUNTRIES, COMMON_LANGUAGES, countryName, languageName, parseCountryInput } from "@/lib/format";
import type { Profile } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { CvImport, type CvSelection } from "./cv-import";
import { type ProfileFormValues, profileSchema, toPayload } from "./schema";

const COUNTRY_INPUT = parseCountryInput;

function defaults(p: Profile): ProfileFormValues {
  return {
    full_name: p.full_name ?? "",
    contact_email: p.contact_email ?? "",
    phone: p.phone ?? "",
    city: p.city ?? "",
    country_of_residence: p.country_of_residence ?? "",
    nationalities: p.nationalities,
    headline: p.headline ?? "",
    summary: p.summary ?? "",
    study_level: p.study_level ?? "",
    current_degree: p.current_degree ?? "",
    institution: p.institution ?? "",
    field_of_study: p.field_of_study ?? "",
    academic_year: p.academic_year ?? "",
    expected_graduation: p.expected_graduation ?? "",
    academic_results: p.academic_results ?? "",
    skills: p.skills,
    experiences: p.experiences.map((e) => ({ ...e, organization: e.organization ?? "", start: e.start ?? "", end: e.end ?? "", description: e.description ?? "" })),
    projects: p.projects.map((x) => ({ ...x, description: x.description ?? "", url: x.url ?? "" })),
    leadership: p.leadership.map((x) => ({ ...x, organization: x.organization ?? "", start: x.start ?? "", end: x.end ?? "", description: x.description ?? "" })),
    languages: p.languages,
    target_countries: p.target_countries,
    internship_fields: p.internship_fields,
    master_fields: p.master_fields,
    funding_preference: p.funding_preference ?? "",
    program_types: p.program_types,
    internship_duration_min_months: p.internship_duration_min_months,
    internship_duration_max_months: p.internship_duration_max_months,
    accepts_remote: p.accepts_remote,
  };
}

export function ProfileView() {
  const { data, error, isLoading, mutate } = useApi<Profile>("profile");
  if (isLoading) return <LoadingState rows={6} />;
  if (error || !data) return <ErrorState onRetry={() => mutate()} />;
  return <ProfileForm profile={data} onSaved={(p) => mutate(p, { revalidate: false })} />;
}

function ProfileForm({ profile, onSaved }: { profile: Profile; onSaved: (p: Profile) => void }) {
  const { notify } = useToast();
  const [serverError, setServerError] = useState<string | null>(null);
  const form = useForm<ProfileFormValues>({ resolver: zodResolver(profileSchema) as Resolver<ProfileFormValues>, defaultValues: defaults(profile) });
  const { register, control, handleSubmit, formState, reset, setValue, getValues } = form;
  const experiences = useFieldArray({ control, name: "experiences" });
  const projects = useFieldArray({ control, name: "projects" });
  const leadership = useFieldArray({ control, name: "leadership" });
  const languages = useFieldArray({ control, name: "languages" });
  useEffect(() => reset(defaults(profile)), [profile, reset]);

  async function onSubmit(values: ProfileFormValues) {
    setServerError(null);
    try {
      const saved = await api<Profile>("profile", { method: "PUT", json: toPayload(values) });
      onSaved(saved);
      notify("Profil enregistré. Les scores sont recalculés.");
    } catch (err) {
      setServerError(errorMessage(err));
    }
  }

  function applyCv(sel: CvSelection) {
    const opts = { shouldDirty: true };
    if (sel.full_name) setValue("full_name", sel.full_name, opts);
    if (sel.contact_email) setValue("contact_email", sel.contact_email, opts);
    if (sel.phone) setValue("phone", sel.phone, opts);
    if (sel.skills) setValue("skills", Array.from(new Set([...getValues("skills"), ...sel.skills])), opts);
    if (sel.languages) {
      const existing = new Set(getValues("languages").map((l) => l.code));
      sel.languages.filter((l) => !existing.has(l.code)).forEach((l) => languages.append(l));
    }
  }

  const err = formState.errors;
  return (
    <>
      <PageHeader
        eyebrow="Votre profil"
        title={t.nav.profile}
        description="Ces informations servent uniquement au calcul d'éligibilité et de compatibilité. Laissez vide ce que vous ne souhaitez pas renseigner : rien n'est supposé."
      />
      <div className="mb-6 grid gap-6 lg:grid-cols-[1fr_1.2fr]">
        <Card title="Complétude">
          <ProgressBar value={profile.completeness} label="Profil complété" />
          {profile.missing_fields.length > 0 && <p className="mt-3 text-sm text-ink-soft">À compléter : {profile.missing_fields.join(", ")}.</p>}
        </Card>
        <CvImport onApply={applyCv} />
      </div>

      <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-6">
        <Card title="Identité & contact">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Field label="Nom complet" error={err.full_name?.message}>{(p) => <Input {...p} autoComplete="name" {...register("full_name")} />}</Field>
            <Field label="E-mail de contact" error={err.contact_email?.message}>{(p) => <Input {...p} type="email" {...register("contact_email")} />}</Field>
            <Field label="Téléphone">{(p) => <Input {...p} type="tel" {...register("phone")} />}</Field>
            <Field label="Ville">{(p) => <Input {...p} {...register("city")} />}</Field>
            <Field label="Pays de résidence" hint="Facultatif">{(p) => (
              <Select {...p} {...register("country_of_residence")}>
                <option value="">Non renseigné</option>
                {COMMON_COUNTRIES.map((c) => <option key={c} value={c}>{countryName(c)}</option>)}
              </Select>
            )}</Field>
            <Controller control={control} name="nationalities" render={({ field }) => (
              <TagInput label="Nationalité(s)" hint="Code ISO (SN, FR…) ou nom du pays. Utilisée seulement pour l'éligibilité." value={field.value} onChange={field.onChange}
                normalize={COUNTRY_INPUT} renderTag={countryName} suggestions={COMMON_COUNTRIES.map(countryName)} max={5} />
            )} />
            <Field label="Titre / accroche" className="sm:col-span-2 lg:col-span-3">{(p) => <Input {...p} {...register("headline")} placeholder="ex. Étudiante en informatique passionnée de données" />}</Field>
            <Field label="Résumé" className="sm:col-span-2 lg:col-span-3">{(p) => <Textarea {...p} {...register("summary")} />}</Field>
          </div>
        </Card>

        <Card title="Études">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Field label="Niveau d'études">{(p) => (
              <Select {...p} {...register("study_level")}>
                <option value="">Non renseigné</option>
                {Object.entries(t.studyLevel).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </Select>
            )}</Field>
            <Field label="Diplôme actuel">{(p) => <Input {...p} {...register("current_degree")} />}</Field>
            <Field label="Établissement">{(p) => <Input {...p} {...register("institution")} />}</Field>
            <Field label="Domaine d'études">{(p) => <Input {...p} {...register("field_of_study")} placeholder="ex. Informatique" />}</Field>
            <Field label="Année académique">{(p) => <Input {...p} {...register("academic_year")} placeholder="ex. L3, M1" />}</Field>
            <Field label="Graduation prévue">{(p) => <Input {...p} type="date" {...register("expected_graduation")} />}</Field>
            <Field label="Résultats académiques" hint="Facultatif, tels qu'ils figurent sur vos relevés." className="sm:col-span-2 lg:col-span-3">{(p) => <Input {...p} {...register("academic_results")} placeholder="ex. Moyenne 14,8/20 — mention Bien" />}</Field>
          </div>
        </Card>

        <Card title="Compétences & langues">
          <div className="flex flex-col gap-4">
            <Controller control={control} name="skills" render={({ field }) => (
              <TagInput label="Compétences techniques" hint="Entrée ou virgule pour ajouter." value={field.value} onChange={field.onChange} placeholder="Python, SQL, Figma…" />
            )} />
            <fieldset className="flex flex-col gap-2">
              <legend className="mb-1 text-sm font-bold">Langues</legend>
              {languages.fields.map((f, i) => (
                <div key={f.id} className="flex flex-wrap items-end gap-2">
                  <Field label="Langue" className="min-w-40 flex-1">{(p) => (
                    <Select {...p} {...register(`languages.${i}.code` as const)}>
                      {COMMON_LANGUAGES.map((c) => <option key={c} value={c}>{languageName(c)}</option>)}
                    </Select>
                  )}</Field>
                  <Field label="Niveau (CECRL)" className="w-40">{(p) => (
                    <Select {...p} {...register(`languages.${i}.level` as const)}>
                      {CEFR_LEVELS.map((l) => <option key={l} value={l}>{l === "native" ? "Langue maternelle" : l}</option>)}
                    </Select>
                  )}</Field>
                  <Button variant="ghost" onClick={() => languages.remove(i)} aria-label="Retirer cette langue"><Trash2 className="size-4" aria-hidden /></Button>
                </div>
              ))}
              {err.languages?.message && <p role="alert" className="text-sm font-semibold text-danger">{err.languages.message}</p>}
              <Button variant="secondary" size="sm" className="self-start" icon={<Plus className="size-4" aria-hidden />}
                onClick={() => languages.append({ code: COMMON_LANGUAGES.find((c) => !getValues("languages").some((l) => l.code === c)) ?? "en", level: "B2" })}>
                Ajouter une langue
              </Button>
            </fieldset>
          </div>
        </Card>

        <Card title="Expériences professionnelles">
          <div className="flex flex-col gap-4">
            {experiences.fields.map((f, i) => (
              <fieldset key={f.id} className="grid gap-3 border-2 border-ink p-3 sm:grid-cols-2 lg:grid-cols-4">
                <legend className="px-1 text-sm font-bold">Expérience {i + 1}</legend>
                <Field label="Intitulé" error={err.experiences?.[i]?.title?.message} className="lg:col-span-2">{(p) => <Input {...p} {...register(`experiences.${i}.title` as const)} />}</Field>
                <Field label="Organisation" className="lg:col-span-2">{(p) => <Input {...p} {...register(`experiences.${i}.organization` as const)} />}</Field>
                <Field label="Début (AAAA-MM)" error={err.experiences?.[i]?.start?.message}>{(p) => <Input {...p} {...register(`experiences.${i}.start` as const)} placeholder="2025-06" />}</Field>
                <Field label="Fin (AAAA-MM)" error={err.experiences?.[i]?.end?.message}>{(p) => <Input {...p} {...register(`experiences.${i}.end` as const)} />}</Field>
                <Field label="Description" className="sm:col-span-2 lg:col-span-4">{(p) => <Textarea {...p} rows={3} {...register(`experiences.${i}.description` as const)} />}</Field>
                <Button variant="danger" size="sm" className="self-start" onClick={() => experiences.remove(i)} icon={<Trash2 className="size-4" aria-hidden />}>Retirer</Button>
              </fieldset>
            ))}
            <Button variant="secondary" size="sm" className="self-start" icon={<Plus className="size-4" aria-hidden />} onClick={() => experiences.append({ title: "", organization: "", start: "", end: "", description: "" })}>Ajouter une expérience</Button>
          </div>
        </Card>

        <div className="grid gap-6 lg:grid-cols-2">
          <Card title="Projets">
            <div className="flex flex-col gap-4">
              {projects.fields.map((f, i) => (
                <fieldset key={f.id} className="flex flex-col gap-3 border-2 border-ink p-3">
                  <legend className="px-1 text-sm font-bold">Projet {i + 1}</legend>
                  <Field label="Nom" error={err.projects?.[i]?.name?.message}>{(p) => <Input {...p} {...register(`projects.${i}.name` as const)} />}</Field>
                  <Field label="Lien">{(p) => <Input {...p} type="url" {...register(`projects.${i}.url` as const)} />}</Field>
                  <Field label="Description">{(p) => <Textarea {...p} rows={2} {...register(`projects.${i}.description` as const)} />}</Field>
                  <Button variant="danger" size="sm" className="self-start" onClick={() => projects.remove(i)}>Retirer</Button>
                </fieldset>
              ))}
              <Button variant="secondary" size="sm" className="self-start" icon={<Plus className="size-4" aria-hidden />} onClick={() => projects.append({ name: "", description: "", url: "" })}>Ajouter un projet</Button>
            </div>
          </Card>
          <Card title="Associatif & leadership">
            <div className="flex flex-col gap-4">
              {leadership.fields.map((f, i) => (
                <fieldset key={f.id} className="flex flex-col gap-3 border-2 border-ink p-3">
                  <legend className="px-1 text-sm font-bold">Engagement {i + 1}</legend>
                  <Field label="Rôle" error={err.leadership?.[i]?.role?.message}>{(p) => <Input {...p} {...register(`leadership.${i}.role` as const)} />}</Field>
                  <Field label="Organisation">{(p) => <Input {...p} {...register(`leadership.${i}.organization` as const)} />}</Field>
                  <Field label="Description">{(p) => <Textarea {...p} rows={2} {...register(`leadership.${i}.description` as const)} />}</Field>
                  <Button variant="danger" size="sm" className="self-start" onClick={() => leadership.remove(i)}>Retirer</Button>
                </fieldset>
              ))}
              <Button variant="secondary" size="sm" className="self-start" icon={<Plus className="size-4" aria-hidden />} onClick={() => leadership.append({ role: "", organization: "", description: "" })}>Ajouter un engagement</Button>
            </div>
          </Card>
        </div>

        <Card title="Préférences de recherche">
          <div className="grid gap-4 lg:grid-cols-2">
            <Controller control={control} name="target_countries" render={({ field }) => (
              <TagInput label="Pays souhaités" hint="Vide = tous les pays conviennent." value={field.value} onChange={field.onChange}
                normalize={COUNTRY_INPUT} renderTag={countryName} suggestions={COMMON_COUNTRIES.map(countryName)} />
            )} />
            <Field label="Préférence de financement">{(p) => (
              <Select {...p} {...register("funding_preference")}>
                <option value="">Non renseignée</option>
                {Object.entries(t.fundingPreference).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </Select>
            )}</Field>
            <Controller control={control} name="internship_fields" render={({ field }) => (
              <TagInput label="Domaines de stage recherchés" value={field.value} onChange={field.onChange} placeholder="data science, énergie…" />
            )} />
            <Controller control={control} name="master_fields" render={({ field }) => (
              <TagInput label="Domaines de master recherchés" value={field.value} onChange={field.onChange} />
            )} />
            <Controller control={control} name="program_types" render={({ field }) => (
              <fieldset className="flex flex-col gap-2">
                <legend className="mb-1 text-sm font-bold">Types de programmes</legend>
                {(["internship", "masters_scholarship"] as const).map((type) => (
                  <Checkbox key={type} label={t.opportunityType[type]} checked={field.value.includes(type)}
                    onChange={(e) => field.onChange(e.target.checked ? [...field.value, type] : field.value.filter((v) => v !== type))} />
                ))}
              </fieldset>
            )} />
            <div className="grid grid-cols-2 gap-3">
              <Field label="Durée de stage min. (mois)">{(p) => <Input {...p} type="number" min={0} max={36} {...register("internship_duration_min_months", { setValueAs: (v) => (v === "" || v === null ? null : Number(v)) })} />}</Field>
              <Field label="Durée max. (mois)" error={err.internship_duration_max_months?.message}>{(p) => <Input {...p} type="number" min={0} max={36} {...register("internship_duration_max_months", { setValueAs: (v) => (v === "" || v === null ? null : Number(v)) })} />}</Field>
            </div>
            <Controller control={control} name="accepts_remote" render={({ field }) => (
              <Checkbox label="J'accepte le télétravail" checked={field.value === true} onChange={(e) => field.onChange(e.target.checked ? true : null)} />
            )} />
          </div>
        </Card>

        <div className="sticky bottom-0 z-10 -mx-4 flex flex-col gap-2 border-t-2 border-ink bg-paper px-4 py-3 sm:mx-0 sm:flex-row sm:items-center sm:justify-between">
          <FormError message={serverError} />
          <p className="text-sm text-ink-soft">{formState.isDirty ? "Modifications non enregistrées." : "À jour."}</p>
          <Button type="submit" size="lg" loading={formState.isSubmitting}>{t.common.save}</Button>
        </div>
      </form>
    </>
  );
}
