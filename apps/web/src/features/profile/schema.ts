import { z } from "zod";

const ym = z.string().regex(/^\d{4}(-(0[1-9]|1[0-2]))?$/, "Format AAAA ou AAAA-MM").or(z.literal("")).nullish();
const optional = (max: number) => z.string().max(max).nullish();

/** Validation client calquée sur le schéma serveur (le serveur reste l'autorité). */
export const profileSchema = z
  .object({
    full_name: optional(200),
    contact_email: z.email("E-mail invalide").or(z.literal("")).nullish(),
    phone: optional(50),
    city: optional(120),
    country_of_residence: z.string().regex(/^[A-Z]{2}$/).or(z.literal("")).nullish(),
    nationalities: z.array(z.string().regex(/^[A-Z]{2}$/)).max(5),
    headline: optional(300),
    summary: optional(5000),
    study_level: z.string().nullish(),
    current_degree: optional(200),
    institution: optional(200),
    field_of_study: optional(200),
    academic_year: optional(50),
    expected_graduation: z.string().nullish(),
    academic_results: optional(300),
    skills: z.array(z.string().max(120)).max(100),
    experiences: z.array(z.object({
      title: z.string().min(1, "Intitulé requis").max(200),
      organization: optional(200),
      location: optional(200),
      start: ym,
      end: ym,
      current: z.boolean().optional(),
      description: optional(4000),
      skills: z.array(z.string()).optional(),
    })).max(50),
    projects: z.array(z.object({ name: z.string().min(1, "Nom requis").max(200), description: optional(4000), url: optional(500), skills: z.array(z.string()).optional() })).max(50),
    leadership: z.array(z.object({ role: z.string().min(1, "Rôle requis").max(200), organization: optional(200), start: ym, end: ym, description: optional(4000) })).max(50),
    languages: z.array(z.object({ code: z.string().regex(/^[a-z]{2,3}$/, "Code langue"), level: z.string().min(1, "Niveau requis") })).max(20),
    target_countries: z.array(z.string()).max(60),
    internship_fields: z.array(z.string()).max(100),
    master_fields: z.array(z.string()).max(100),
    funding_preference: z.string().nullish(),
    program_types: z.array(z.string()),
    internship_duration_min_months: z.number().int().min(0).max(36).nullish(),
    internship_duration_max_months: z.number().int().min(0).max(36).nullish(),
    accepts_remote: z.boolean().nullish(),
  })
  .refine((v) => v.internship_duration_min_months == null || v.internship_duration_max_months == null || v.internship_duration_min_months <= v.internship_duration_max_months, {
    path: ["internship_duration_max_months"],
    message: "La durée maximale doit être supérieure à la minimale.",
  })
  .refine((v) => new Set(v.languages.map((l) => l.code)).size === v.languages.length, { path: ["languages"], message: "Chaque langue une seule fois." });

export type ProfileFormValues = z.infer<typeof profileSchema>;

/** Les chaînes vides deviennent null avant l'envoi. */
export function toPayload(values: ProfileFormValues): Record<string, unknown> {
  const clean = (v: unknown): unknown => {
    if (v === "") return null;
    if (Array.isArray(v)) return v.map(clean);
    if (v && typeof v === "object") return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, clean(x)]));
    return v;
  };
  return clean(values) as Record<string, unknown>;
}
