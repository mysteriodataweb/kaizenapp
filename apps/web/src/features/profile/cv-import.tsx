"use client";

import { FileUp } from "lucide-react";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Alert } from "@/components/ui/feedback";
import { Checkbox } from "@/components/ui/form";
import { useToast } from "@/components/ui/toast";
import { api, errorMessage } from "@/lib/api";
import { languageName } from "@/lib/format";
import type { CvExtraction } from "@/lib/types";

export interface CvSelection {
  full_name?: string;
  contact_email?: string;
  phone?: string;
  skills?: string[];
  languages?: { code: string; level: string }[];
}

/**
 * Import de CV : les informations extraites sont seulement PROPOSÉES. L'utilisateur coche ce qu'il
 * veut reprendre, puis enregistre lui-même le profil. Rien n'est inventé ni enregistré automatiquement.
 */
export function CvImport({ onApply }: { onApply: (selection: CvSelection) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const { notify } = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<CvExtraction | null>(null);
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [saveAsDocument, setSaveAsDocument] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function analyse(f: File) {
    setFile(f);
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const body = new FormData();
      body.append("file", f);
      const res = await api<CvExtraction>("profile/cv-extract", { method: "POST", body });
      setResult(res);
      setChecked(Object.fromEntries(Object.keys(res.suggestions).map((k) => [k, true])));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  async function apply() {
    if (!result) return;
    const s = result.suggestions;
    const selection: CvSelection = {};
    if (checked.full_name && s.full_name) selection.full_name = s.full_name;
    if (checked.contact_email && s.contact_email) selection.contact_email = s.contact_email;
    if (checked.phone && s.phone) selection.phone = s.phone;
    if (checked.skills && s.skills) selection.skills = s.skills;
    if (checked.languages && s.languages) selection.languages = s.languages.filter((l) => l.level).map((l) => ({ code: l.code, level: l.level as string }));
    onApply(selection);
    if (saveAsDocument && file) {
      const body = new FormData();
      body.append("file", file);
      body.append("doc_type", "cv");
      body.append("title", file.name.replace(/\.pdf$/i, ""));
      await api("documents", { method: "POST", body }).then(
        () => notify("CV ajouté à vos documents."),
        (err) => notify(`CV non archivé : ${errorMessage(err)}`, "error"),
      );
    }
    notify("Suggestions reportées dans le formulaire : vérifiez puis enregistrez.");
    setResult(null);
  }

  const s = result?.suggestions;
  const rows: { key: string; label: string; value: string | undefined }[] = s ? [
    { key: "full_name", label: "Nom", value: s.full_name },
    { key: "contact_email", label: "E-mail", value: s.contact_email },
    { key: "phone", label: "Téléphone", value: s.phone },
    { key: "skills", label: "Compétences", value: s.skills?.join(", ") },
    { key: "languages", label: "Langues", value: s.languages?.map((l) => `${languageName(l.code)} ${l.level ?? "(niveau à préciser)"}`).join(", ") },
  ].filter((r) => r.value) : [];

  return (
    <Card title="Importer un CV (PDF)" description="Extraction prudente : seules les informations présentes dans le document sont proposées, avec l'extrait qui les justifie.">
      <input ref={input} type="file" accept="application/pdf" className="sr-only" id="cv-file" onChange={(e) => e.target.files?.[0] && analyse(e.target.files[0])} />
      <Button variant="secondary" loading={loading} icon={<FileUp className="size-4" aria-hidden />} onClick={() => input.current?.click()}>Choisir un PDF</Button>
      {error && <Alert tone="danger" className="mt-3">{error}</Alert>}
      {result && (
        <div className="mt-4 flex flex-col gap-3">
          {result.warnings.map((w) => <Alert key={w} tone="warning">{w}</Alert>)}
          {rows.length === 0 ? <p className="text-sm">Aucune information exploitable trouvée.</p> : (
            <fieldset className="flex flex-col gap-3">
              <legend className="mb-2 text-sm font-bold">Cochez les informations à reprendre :</legend>
              {rows.map((r) => (
                <Checkbox key={r.key} label={`${r.label} : ${r.value}`}
                  description={result.evidence[r.key] ? `Extrait : « ${result.evidence[r.key]} »` : undefined}
                  checked={checked[r.key] ?? false} onChange={(e) => setChecked({ ...checked, [r.key]: e.target.checked })} />
              ))}
            </fieldset>
          )}
          {s?.study_level_mentioned && (
            <p className="text-sm">Diplôme mentionné : <strong>{s.study_level_mentioned}</strong> — non repris automatiquement (obtenu ou en cours ?), à saisir vous-même.</p>
          )}
          <Checkbox label="Ajouter aussi ce fichier à mes documents (CV)" checked={saveAsDocument} onChange={(e) => setSaveAsDocument(e.target.checked)} />
          <div className="flex gap-2">
            <Button onClick={apply} disabled={rows.length === 0}>Reporter dans le formulaire</Button>
            <Button variant="ghost" onClick={() => setResult(null)}>Ignorer</Button>
          </div>
        </div>
      )}
    </Card>
  );
}
