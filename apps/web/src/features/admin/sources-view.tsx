"use client";

import { FlaskConical, Play, Settings2 } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { type Column, DataTable } from "@/components/ui/data-table";
import { Alert, EmptyState, ErrorState, LoadingState } from "@/components/ui/feedback";
import { Checkbox, Field, FormError, Input, Textarea } from "@/components/ui/form";
import { Modal } from "@/components/ui/modal";
import { PageHeader } from "@/components/ui/page-header";
import { useToast } from "@/components/ui/toast";
import { VerificationBadge } from "@/features/shared/badges";
import { useUser } from "@/features/shared/user-context";
import { label, t } from "@/i18n";
import { api, errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { IngestionRun, Source, SourceTestResult } from "@/lib/types";
import { useApi } from "@/lib/use-api";

export function SourcesView() {
  const user = useUser();
  const tz = user.timezone;
  const { notify } = useToast();
  const { data: sources, error, isLoading, mutate } = useApi<Source[]>(user.is_admin ? "admin/sources" : null);
  const { data: runs, mutate: mutateRuns } = useApi<IngestionRun[]>(user.is_admin ? "admin/runs?limit=30" : null, { refreshInterval: 15000 });
  const [testing, setTesting] = useState<string | null>(null);
  const [result, setResult] = useState<SourceTestResult | null>(null);
  const [editing, setEditing] = useState<Source | null>(null);

  if (!user.is_admin) return <Alert tone="danger" title="Accès réservé à l'administrateur." />;
  if (isLoading) return <LoadingState rows={4} />;
  if (error || !sources) return <ErrorState onRetry={() => mutate()} />;

  async function toggle(source: Source) {
    try {
      await api(`admin/sources/${source.id}`, { method: "PATCH", json: { enabled: !source.enabled } });
      await mutate();
    } catch (err) {
      notify(errorMessage(err), "error");
    }
  }

  async function test(source: Source) {
    setTesting(source.id);
    try {
      setResult(await api<SourceTestResult>(`admin/sources/${source.id}/test`, { method: "POST" }));
      await mutate();
    } catch (err) {
      notify(errorMessage(err), "error");
    } finally {
      setTesting(null);
    }
  }

  async function collect(source?: Source) {
    try {
      const res = await api<{ message: string }>(`admin/collect${source ? `?source_id=${source.id}` : ""}`, { method: "POST" });
      notify(res.message);
      setTimeout(() => void mutateRuns(), 3000);
    } catch (err) {
      notify(errorMessage(err), "error");
    }
  }

  const runColumns: Column<IngestionRun>[] = [
    { key: "date", header: "Début", cell: (r) => formatDate(r.started_at, tz, true) },
    { key: "source", header: "Source", cell: (r) => sources.find((s) => s.id === r.source_id)?.name ?? "—" },
    { key: "by", header: "Déclencheur", cell: (r) => r.triggered_by },
    { key: "status", header: "Statut", cell: (r) => <Badge tone={r.status === "success" ? "success" : r.status === "failed" ? "danger" : "accent"}>{label(t.runStatus, r.status)}</Badge> },
    { key: "counts", header: "Résultat", cell: (r) => `${r.items_fetched} lues · ${r.items_created} créées · ${r.items_updated} maj · ${r.items_skipped} ignorées` },
    { key: "errors", header: "Erreurs", cell: (r) => r.details.fatal ?? (r.errors_count ? `${r.errors_count} : ${r.details.errors?.[0]?.error ?? ""}` : "—") },
  ];

  return (
    <>
      <PageHeader eyebrow="Administration" title="Sources de veille"
        description="Seules les sources publiques et autorisées sont interrogées (robots.txt respecté, débit limité, aucun contournement). Testez une source avant de l'activer."
        actions={<Button onClick={() => collect()} icon={<Play className="size-4" aria-hidden />}>Collecter maintenant</Button>} />
      <div className="grid gap-4 lg:grid-cols-2">
        {sources.map((s) => (
          <Card key={s.id} as="article" title={s.name} description={s.description ?? undefined}
            actions={<Checkbox label={s.enabled ? "Active" : "Inactive"} checked={s.enabled} onChange={() => toggle(s)} />}>
            <div className="mb-3 flex flex-wrap gap-1.5">
              <Badge tone="outline">{s.connector}</Badge>
              <VerificationBadge value={s.verification_status} />
              <Badge tone="neutral">{s.opportunities_count} annonce(s)</Badge>
              {s.consecutive_failures > 0 && <Badge tone="danger">{s.consecutive_failures} échec(s) consécutif(s)</Badge>}
            </div>
            <dl className="grid grid-cols-2 gap-2 text-sm">
              <dt className="font-bold">Dernière collecte</dt><dd>{formatDate(s.last_run_at, tz, true)}</dd>
              <dt className="font-bold">Dernier succès</dt><dd>{formatDate(s.last_success_at, tz, true)}</dd>
              <dt className="font-bold">Débit</dt><dd>1 requête / {s.rate_limit_seconds} s · {s.max_items} max</dd>
            </dl>
            {s.terms_notes && <p className="mt-2 text-xs text-ink-soft">{s.terms_notes}</p>}
            {s.last_error && <Alert tone="danger" className="mt-3">{s.last_error}</Alert>}
            <div className="mt-4 flex flex-wrap gap-2">
              <Button size="sm" variant="secondary" loading={testing === s.id} onClick={() => test(s)} icon={<FlaskConical className="size-4" aria-hidden />}>Tester (à blanc)</Button>
              <Button size="sm" variant="secondary" onClick={() => setEditing(s)} icon={<Settings2 className="size-4" aria-hidden />}>Configurer</Button>
              <Button size="sm" variant="ink" onClick={() => collect(s)} icon={<Play className="size-4" aria-hidden />}>Collecter</Button>
            </div>
          </Card>
        ))}
      </div>
      <section className="mt-8">
        <h2 className="mb-3 text-2xl font-black uppercase">Exécutions récentes</h2>
        <DataTable rows={runs ?? []} columns={runColumns} rowKey={(r) => r.id} caption="Exécutions de collecte" empty={<EmptyState title="Aucune exécution" />} />
      </section>

      <Modal open={result !== null} onClose={() => setResult(null)} title={result?.ok ? "Source exploitable" : "Test échoué"}
        description={result ? `${result.items_found} annonce(s) valides trouvées en ${result.duration_ms} ms. Rien n'a été enregistré.` : undefined}>
        {result?.errors.map((e) => <Alert key={e} tone="danger">{e}</Alert>)}
        {result && result.sample.length > 0 && (
          <ul className="flex flex-col gap-2 text-sm">
            {result.sample.map((s) => (
              <li key={s.official_url} className="border-2 border-ink p-2">
                <p className="font-bold">{s.title}</p>
                <p>{s.organization} · {s.countries.join(", ") || "pays non précisé"} · date : {s.deadline_status}</p>
                <a href={s.official_url} target="_blank" rel="noopener noreferrer" className="break-all text-xs underline">{s.official_url}</a>
              </li>
            ))}
          </ul>
        )}
      </Modal>
      {editing && <ConfigModal source={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); void mutate(); }} />}
    </>
  );
}

function ConfigModal({ source, onClose, onSaved }: { source: Source; onClose: () => void; onSaved: () => void }) {
  const [config, setConfig] = useState(JSON.stringify(source.config, null, 2));
  const [rate, setRate] = useState(String(source.rate_limit_seconds));
  const [maxItems, setMaxItems] = useState(String(source.max_items));
  const [error, setError] = useState<string | null>(null);
  async function save() {
    let parsed: unknown;
    try {
      parsed = JSON.parse(config);
    } catch {
      return setError("JSON invalide.");
    }
    try {
      await api(`admin/sources/${source.id}`, { method: "PATCH", json: { config: parsed as Record<string, unknown>, rate_limit_seconds: Number(rate), max_items: Number(maxItems) } });
      onSaved();
    } catch (err) {
      setError(errorMessage(err));
    }
  }
  return (
    <Modal open onClose={onClose} title={`Configurer : ${source.name}`}
      description="Exemples — Greenhouse : {&quot;boards&quot;: [{&quot;token&quot;: &quot;entreprise&quot;, &quot;organization&quot;: &quot;Entreprise&quot;}]} · RSS : {&quot;feeds&quot;: [{&quot;url&quot;: &quot;https://…&quot;, &quot;type&quot;: &quot;auto&quot;, &quot;official&quot;: true}]}"
      footer={<><Button variant="secondary" onClick={onClose}>Annuler</Button><Button onClick={save}>Enregistrer</Button></>}>
      <Field label="Configuration (JSON)">{(p) => <Textarea {...p} rows={12} className="font-mono text-sm" value={config} onChange={(e) => setConfig(e.target.value)} />}</Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Délai entre requêtes (s)" hint="0,5 à 60">{(p) => <Input {...p} type="number" step="0.5" min={0.5} max={60} value={rate} onChange={(e) => setRate(e.target.value)} />}</Field>
        <Field label="Annonces max. par collecte">{(p) => <Input {...p} type="number" min={1} max={2000} value={maxItems} onChange={(e) => setMaxItems(e.target.value)} />}</Field>
      </div>
      <FormError message={error} />
    </Modal>
  );
}
