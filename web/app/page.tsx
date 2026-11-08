import { Hero } from "@/components/landing/Hero";
import { PersonalNote } from "@/components/landing/PersonalNote";
import { Topics } from "@/components/landing/Topics";
import { HowItWorks } from "@/components/landing/HowItWorks";
import { Footer } from "@/components/landing/Footer";

export default function LandingPage() {
  // Always show the landing page — not gated, no redirect for signed-in users.
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
