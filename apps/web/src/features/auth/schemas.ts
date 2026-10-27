import { z } from "zod";

export const loginSchema = z.object({
  email: z.email("Adresse e-mail invalide."),
  password: z.string().min(1, "Mot de passe requis."),
});
export type LoginValues = z.infer<typeof loginSchema>;

/** Mêmes règles que le serveur (le serveur reste l'autorité). */
export const newPasswordSchema = z
  .object({
    password: z.string().min(12, "12 caractères minimum.").max(256),
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, { path: ["confirm"], message: "Les mots de passe ne correspondent pas." })
  .refine((v) => new Set(v.password).size >= 6, { path: ["password"], message: "Mot de passe trop répétitif." });
