import type { Metadata } from "next";

import { ProfileView } from "@/features/profile/profile-form";

export const metadata: Metadata = { title: "Profil" };

export default function ProfilePage() {
  return <ProfileView />;
}
