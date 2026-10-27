"use client";

import { Copy, Sparkles } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Alert } from "@/components/ui/feedback";
import { Field, Select, Textarea } from "@/components/ui/form";
import { useToast } from "@/components/ui/toast";
import { api, errorMessage } from "@/lib/api";
import type { AssistResult } from "@/lib/types";
import { useApi } from "@/lib/use-api";

const KINDS = {
  cover_letter: "Lettre de motivation",
  cv_tailoring: "Adapter mon CV",
  application_answers: "Réponses aux questions",
  email_draft: "Brouillon d'e-mail",
  interview_prep: "Préparation d'entretien",
};

/** Assistant de rédaction facultatif : brouillon modifiable, jamais envoyé automatiquement. */
export function AssistPanel({ opportunityId, applicationId }: { opportunityId: string; applicationId?: string | null }) {
  const { data: status } = useApi<{ enabled: boolean }>("assist/status");
  const { notify } = useToast();
  const [kind, setKind] = useState<keyof typeof KINDS>("cover_letter");
  const [instructions, setInstructions] = useState("");
  const [questions, setQuestions] = useState("");
  const [result, setResult] = useState<AssistResult | null>(null);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function generate() {
    setLoading(true);
    setError(null);
    try {
      const res = await api<AssistResult>("assist/generate", {
        method: "POST",
        json: {
          kind,
          opportunity_id: opportunityId,
          instructions: instructions || null,
          questions: questions.split("\n").map((q) => q.trim()).filter(Boolean).slice(0, 10),
        },
      });
      setResult(res);
      setDraft(res.draft ?? "");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  async function saveToNotes() {
    if (!applicationId) return;
    try {
      const app = await api<{ notes: string | null }>(`applications/${applicationId}`);
      const notes = [app.notes, `--- ${KINDS[kind]} (brouillon validé) ---\n${draft}`].filter(Boolean).join("\n\n");
      await api(`applications/${applicationId}`, { method: "PATCH", json: { notes } });
      notify("Brouillon ajouté aux notes de la candidature.");
    } catch (err) {
      notify(errorMessage(err), "error");
    }
  }

  return (
    <Card title="Assistant de rédaction" description="Prépare des brouillons à partir de votre profil et de l'annonce uniquement.">
      {status && !status.enabled ? (
        <Alert tone="info" title="Fonction désactivée">
          Aucun fournisseur IA n&apos;est configuré (AI_PROVIDER / AI_API_KEY). Toutes les autres fonctionnalités restent
          disponibles.
        </Alert>
      ) : (
        <div className="flex flex-col gap-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Type de document">{(p) => (
              <Select {...p} value={kind} onChange={(e) => setKind(e.target.value as keyof typeof KINDS)}>
                {Object.entries(KINDS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </Select>
            )}</Field>
            <Field label="Consignes (facultatif)" hint="Ton, longueur, langue…">{(p) => (
              <Textarea {...p} rows={2} value={instructions} onChange={(e) => setInstructions(e.target.value)} />
            )}</Field>
          </div>
          {kind === "application_answers" && (
            <Field label="Questions (une par ligne)">{(p) => <Textarea {...p} value={questions} onChange={(e) => setQuestions(e.target.value)} />}</Field>
          )}
          <Button onClick={generate} loading={loading} icon={<Sparkles className="size-4" aria-hidden />} className="self-start">Générer un brouillon</Button>
          {error && <Alert tone="danger">{error}</Alert>}
          {result && (
            <>
              {result.missing_information.length > 0 && (
                <Alert tone="warning" title="Informations manquantes dans votre profil">
                  {result.missing_information.join(", ")} — elles apparaissent comme [À COMPLÉTER] au lieu d&apos;être inventées.
                </Alert>
              )}
              <Field label="Brouillon (modifiable)" hint={result.warning}>{(p) => (
                <Textarea {...p} rows={14} value={draft} onChange={(e) => setDraft(e.target.value)} />
              )}</Field>
              <div className="flex flex-wrap gap-2">
                <Button variant="secondary" size="sm" icon={<Copy className="size-4" aria-hidden />} onClick={() => navigator.clipboard.writeText(draft).then(() => notify("Copié."))}>Copier</Button>
                {applicationId && <Button size="sm" onClick={saveToNotes}>Valider et ajouter aux notes</Button>}
              </div>
            </>
          )}
        </div>
      )}
    </Card>
  );
}
