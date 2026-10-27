import { LinkButton } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main className="grid min-h-dvh place-items-center bg-muted p-6">
      <div className="brutal-card max-w-md p-8 text-center">
        <p className="font-display text-7xl font-black" style={{ fontStretch: "75%" }}>404</p>
        <p className="mt-2 text-lg font-bold">Page introuvable.</p>
        <LinkButton href="/dashboard" variant="primary" className="mt-6">Retour au tableau de bord</LinkButton>
      </div>
    </main>
  );
}
