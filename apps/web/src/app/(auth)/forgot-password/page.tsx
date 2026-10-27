import type { Metadata } from "next";

import { ForgotPasswordForm } from "@/features/auth/password-forms";

export const metadata: Metadata = { title: "Mot de passe oublié" };

export default function ForgotPasswordPage() {
  return <ForgotPasswordForm />;
}
