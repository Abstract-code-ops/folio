import { Hero } from "@/components/landing/Hero";
import { PersonalNote } from "@/components/landing/PersonalNote";
import { Topics } from "@/components/landing/Topics";
import { HowItWorks } from "@/components/landing/HowItWorks";
import { Footer } from "@/components/landing/Footer";

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-bg-base">
      <Hero />
      <PersonalNote />
      <Topics />
      <HowItWorks />
      <Footer />
    </div>
  );
}
