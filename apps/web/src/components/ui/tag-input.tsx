"use client";

import { X } from "lucide-react";
import { type KeyboardEvent, useId, useState } from "react";

interface TagInputProps {
  label: string;
  value: string[];
  onChange: (value: string[]) => void;
  placeholder?: string;
  hint?: string;
  suggestions?: string[];
  renderTag?: (tag: string) => string;
  normalize?: (tag: string) => string | null;
  max?: number;
}

/** Saisie de liste (compétences, pays…) : Entrée ou virgule pour ajouter, bouton pour retirer. */
export function TagInput({ label, value, onChange, placeholder, hint, suggestions, renderTag, normalize, max = 100 }: TagInputProps) {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const id = useId();
  const listId = `${id}-list`;

  function add(raw: string) {
    const cleaned = raw.trim();
    if (!cleaned) return;
    const tag = normalize ? normalize(cleaned) : cleaned;
    if (!tag) {
      setError(`« ${cleaned} » n'est pas une valeur valide.`);
      return;
    }
    if (value.some((v) => v.toLowerCase() === tag.toLowerCase())) {
      setDraft("");
      return;
    }
    if (value.length >= max) return;
    onChange([...value, tag]);
    setDraft("");
    setError(null);
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      add(draft);
    } else if (e.key === "Backspace" && !draft && value.length) {
      onChange(value.slice(0, -1));
    }
  }

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-bold">{label}</label>
      <div className="flex min-h-11 flex-wrap items-center gap-1.5 border-2 border-ink bg-paper p-1.5 focus-within:shadow-[var(--shadow-brutal-sm)]">
        {value.map((tag) => (
          <span key={tag} className="inline-flex items-center gap-1 border-2 border-ink bg-accent-soft px-1.5 py-0.5 text-sm font-semibold">
            {renderTag ? renderTag(tag) : tag}
            <button type="button" onClick={() => onChange(value.filter((v) => v !== tag))} aria-label={`Retirer ${renderTag ? renderTag(tag) : tag}`} className="grid size-5 place-items-center hover:bg-accent">
              <X className="size-3.5" aria-hidden />
            </button>
          </span>
        ))}
        <input
          id={id}
          value={draft}
          list={suggestions ? listId : undefined}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          onBlur={() => add(draft)}
          placeholder={value.length ? "" : placeholder}
          aria-describedby={hint ? `${id}-hint` : undefined}
          className="h-8 min-w-32 flex-1 bg-transparent px-1 text-[15px] outline-none"
        />
        {suggestions && (
          <datalist id={listId}>
            {suggestions.map((s) => (
              <option key={s} value={s}>{renderTag ? renderTag(s) : s}</option>
            ))}
          </datalist>
        )}
      </div>
      {hint && <p id={`${id}-hint`} className="text-xs text-ink-soft">{hint}</p>}
      {error && <p role="alert" className="text-sm font-semibold text-danger">{error}</p>}
    </div>
  );
}
