import { Footer } from "@/components/landing/footer";
import { Header } from "@/components/landing/header";
import { Hero } from "@/components/landing/hero";
import { RagExamples } from "@/components/landing/rag-examples";
import { WhatsNewSection } from "@/components/landing/sections/whats-new-section";

export default function LandingPage() {
  return (
    <div className="min-h-screen w-full overflow-x-clip bg-[#0a0a0a]">
      <Header />
      <main className="flex w-full flex-col">
        <Hero />
        <RagExamples />
        <WhatsNewSection />
      </main>
      <Footer />
    </div>
  );
}
