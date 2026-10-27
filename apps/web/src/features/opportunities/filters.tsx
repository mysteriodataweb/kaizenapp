"use client";

import { Filter, RotateCcw, Search } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox, Field, Input, Select } from "@/components/ui/form";
import { t } from "@/i18n";
import { countryName } from "@/lib/format";
import { APPLICATION_STATUSES, type Facets } from "@/lib/types";

export type FilterState = Record<string, string>;

export const DEFAULT_SORT = "-score";

interface FiltersProps {
  value: FilterState;
  facets?: Facets;
  onChange: (next: FilterState) => void;
}

export function OpportunityFilters({ value, facets, onChange }: FiltersProps) {
  const [q, setQ] = useState(value.q ?? "");
  const [open, setOpen] = useState(false);
  const [lastQ, setLastQ] = useState(value.q ?? "");
  if ((value.q ?? "") !== lastQ) {
    // L'URL a changé (retour arrière, réinitialisation) : on resynchronise le champ de recherche.
    setLastQ(value.q ?? "");
    setQ(value.q ?? "");
  }
  useEffect(() => {
    const id = setTimeout(() => {
      if ((value.q ?? "") !== q) onChange({ ...value, q, page: "1" });
    }, 350);
    return () => clearTimeout(id);
  }, [q]); // eslint-disable-line react-hooks/exhaustive-deps

  const set = (key: string, v: string) => onChange({ ...value, [key]: v, page: "1" });
  const activeCount = Object.entries(value).filter(([k, v]) => v && !["page", "sort", "q"].includes(k)).length;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-2 sm:flex-row">
        <div className="relative flex-1">
          <label htmlFor="search" className="sr-only">Rechercher</label>
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2" aria-hidden />
          <Input id="search" type="search" placeholder="Rechercher : titre, organisme, mots-clés…" value={q} onChange={(e) => setQ(e.target.value)} className="pl-9" />
        </div>
        <div className="flex gap-2">
          <label htmlFor="sort" className="sr-only">Trier</label>
          <Select id="sort" value={value.sort ?? DEFAULT_SORT} onChange={(e) => set("sort", e.target.value)} className="sm:w-56">
            <option value="-score">Meilleure compatibilité</option>
            <option value="deadline">Échéance la plus proche</option>
            <option value="recent">Plus récentes</option>
            <option value="title">Titre (A→Z)</option>
          </Select>
          <Button variant={open || activeCount ? "primary" : "secondary"} onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-controls="filters-panel" icon={<Filter className="size-4" aria-hidden />}>
            Filtres{activeCount ? ` (${activeCount})` : ""}
          </Button>
        </div>
      </div>

      {open && (
        <div id="filters-panel" className="brutal-card grid gap-4 p-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Type">{(p) => (
            <Select {...p} value={value.type ?? ""} onChange={(e) => set("type", e.target.value)}>
              <option value="">Tous</option>
              <option value="internship">{t.opportunityType.internship}</option>
              <option value="masters_scholarship">{t.opportunityType.masters_scholarship}</option>
            </Select>
          )}</Field>
          <Field label="Pays">{(p) => (
            <Select {...p} value={value.country ?? ""} onChange={(e) => set("country", e.target.value)}>
              <option value="">Tous</option>
              {(facets?.countries ?? []).map((c) => <option key={c} value={c}>{countryName(c)}</option>)}
            </Select>
          )}</Field>
          <Field label="Domaine">{(p) => (
            <Input {...p} list="fields-list" value={value.field ?? ""} onChange={(e) => set("field", e.target.value)} placeholder="ex. data, énergie" />
          )}</Field>
          <datalist id="fields-list">{(facets?.fields ?? []).map((f) => <option key={f} value={f} />)}</datalist>
          <Field label="Organisme">{(p) => (
            <Input {...p} list="orgs-list" value={value.organization ?? ""} onChange={(e) => set("organization", e.target.value)} />
          )}</Field>
          <datalist id="orgs-list">{(facets?.organizations ?? []).map((o) => <option key={o} value={o} />)}</datalist>
          <Field label="Niveau académique" hint="Inclut les annonces sans niveau précisé.">{(p) => (
            <Select {...p} value={value.study_level ?? ""} onChange={(e) => set("study_level", e.target.value)}>
              <option value="">Tous</option>
              {Object.entries(t.studyLevel).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </Select>
          )}</Field>
          <Field label="Financement">{(p) => (
            <Select {...p} value={value.funding ?? ""} onChange={(e) => set("funding", e.target.value)}>
              <option value="">Tous</option>
              <option value="full">Complet</option>
              <option value="partial">Partiel</option>
              <option value="full_or_partial">Complet ou partiel</option>
            </Select>
          )}</Field>
          <Field label="Échéance">{(p) => (
            <Select {...p} value={value.deadline_within_days ?? ""} onChange={(e) => set("deadline_within_days", e.target.value)}>
              <option value="">Toutes</option>
              <option value="7">Sous 7 jours</option>
              <option value="30">Sous 30 jours</option>
              <option value="90">Sous 3 mois</option>
            </Select>
          )}</Field>
          <Field label="Éligibilité">{(p) => (
            <Select {...p} value={value.eligibility ?? ""} onChange={(e) => set("eligibility", e.target.value)}>
              <option value="">Toutes</option>
              {Object.entries(t.eligibility).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </Select>
          )}</Field>
          <Field label={`Score minimal : ${value.min_score || 0}`}>{(p) => (
            <input {...p} type="range" min={0} max={100} step={5} value={value.min_score || 0} onChange={(e) => set("min_score", e.target.value === "0" ? "" : e.target.value)} className="h-11 accent-[#111]" />
          )}</Field>
          <Field label="Statut dans mes candidatures">{(p) => (
            <Select {...p} value={value.application_status || (value.tracked === "false" ? "__none" : "")} onChange={(e) => {
              const v = e.target.value;
              onChange({ ...value, application_status: v === "__none" ? "" : v, tracked: v === "__none" ? "false" : "", page: "1" });
            }}>
              <option value="">Tous</option>
              <option value="__none">Non suivies</option>
              {APPLICATION_STATUSES.map((s) => <option key={s} value={s}>{t.applicationStatus[s]}</option>)}
            </Select>
          )}</Field>
          <div className="flex flex-col justify-end gap-3 sm:col-span-2">
            <Checkbox label="Favoris uniquement" checked={value.favorites_only === "true"} onChange={(e) => set("favorites_only", e.target.checked ? "true" : "")} />
            <Checkbox label="Inclure les annonces fermées ou échues" checked={value.include_closed === "true"} onChange={(e) => set("include_closed", e.target.checked ? "true" : "")} />
          </div>
          <div className="flex items-end lg:col-span-4">
            <Button variant="ghost" size="sm" onClick={() => onChange({ sort: value.sort ?? DEFAULT_SORT, page: "1" })} icon={<RotateCcw className="size-4" aria-hidden />}>
              Réinitialiser les filtres
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
