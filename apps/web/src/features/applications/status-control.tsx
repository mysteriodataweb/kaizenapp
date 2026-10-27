"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox, Select } from "@/components/ui/form";
import { Modal } from "@/components/ui/modal";
import { useToast } from "@/components/ui/toast";
import { t } from "@/i18n";
import { api, errorMessage } from "@/lib/api";
import { type Application, APPLICATION_STATUSES, type ApplicationStatus, SUBMITTED_STATUSES } from "@/lib/types";

/**
 * Sélecteur de statut. Passer à « Envoyée » (ou au-delà) exige une confirmation humaine explicite :
 * l'application n'envoie jamais de candidature elle-même.
 */
export function StatusControl({ app, onChanged, compact }: { app: Application; onChanged: (a: Application) => void; compact?: boolean }) {
  const { notify } = useToast();
  const [pending, setPending] = useState<ApplicationStatus | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [saving, setSaving] = useState(false);

  async function save(status: ApplicationStatus, confirm = false) {
    setSaving(true);
    try {
      const updated = await api<Application>(`applications/${app.id}`, { method: "PATCH", json: { status, confirm_submission: confirm } });
      onChanged(updated);
      notify(`Statut : ${t.applicationStatus[status]}`);
      setPending(null);
    } catch (err) {
      notify(errorMessage(err), "error");
    } finally {
      setSaving(false);
    }
  }

  function onSelect(status: ApplicationStatus) {
    if (status === app.status) return;
    if (SUBMITTED_STATUSES.includes(status) && !app.submission_confirmed_at) {
      setConfirmed(false);
      setPending(status);
      return;
    }
    void save(status);
  }

  return (
    <>
      <label className={compact ? "sr-only" : "text-sm font-bold"} htmlFor={`status-${app.id}`}>Statut</label>
      <Select id={`status-${app.id}`} value={app.status} disabled={saving} onChange={(e) => onSelect(e.target.value as ApplicationStatus)} className={compact ? "h-9 text-sm" : undefined}>
        {APPLICATION_STATUSES.map((s) => <option key={s} value={s}>{t.applicationStatus[s]}</option>)}
      </Select>
      <Modal
        open={pending !== null}
        onClose={() => setPending(null)}
        title="Confirmer l'envoi"
        description="Opportunity Intelligence n'envoie jamais de candidature à votre place. Ce statut indique que VOUS l'avez soumise sur le site officiel."
        footer={
          <>
            <Button variant="secondary" onClick={() => setPending(null)}>{t.common.cancel}</Button>
            <Button disabled={!confirmed} loading={saving} onClick={() => pending && save(pending, true)}>{t.common.confirm}</Button>
          </>
        }
      >
        <p className="font-semibold">{app.opportunity.title} — {app.opportunity.organization}</p>
        <Checkbox label="J'ai moi-même envoyé cette candidature." description="La date d'envoi sera enregistrée maintenant (modifiable ensuite)." checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
      </Modal>
    </>
  );
}
