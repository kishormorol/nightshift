import { BusySplit } from "@/components/busy-split";
import { DigestPayoff } from "@/components/digest-payoff";
import { Footer } from "@/components/footer";
import { Hero } from "@/components/hero";
import { Nav } from "@/components/nav";
import { Pipeline } from "@/components/pipeline";

export default function Home() {
  return (
    <>
      <a
        href="#top"
        className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-50 focus:rounded-md focus:bg-accent focus:px-4 focus:py-2 focus:font-mono focus:text-sm focus:text-ink"
      >
        Skip to content
      </a>
      <Nav />
      <main className="flex-1">
        <Hero />
        <BusySplit />
        <Pipeline />
        <DigestPayoff />
      </main>
      <Footer />
    </>
  );
}
