import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { auth } from "@/lib/auth";
import { Hero } from "@/components/landing/Hero";
import { PersonalNote } from "@/components/landing/PersonalNote";
import { Topics } from "@/components/landing/Topics";
import { HowItWorks } from "@/components/landing/HowItWorks";
import { Footer } from "@/components/landing/Footer";

export default async function LandingPage() {
  // Signed-in users go straight to their library.
  const session = await auth.api.getSession({ headers: await headers() });
  if (session?.user) redirect("/library");

  return (
    <div className="min-h-screen bg-bg-base font-body">
      <Hero />
      <PersonalNote />
      <Topics />
      <HowItWorks />
      <Footer />
    </div>
  );
}
