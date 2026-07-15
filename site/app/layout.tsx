import type { Metadata } from "next";
import { JetBrains_Mono, Space_Grotesk } from "next/font/google";
import "./globals.css";

const spaceGrotesk = Space_Grotesk({
  variable: "--font-space-grotesk",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

const description =
  "Put your idle Claude Code subscription to work — read-only reviews of your " +
  "projects while you're busy, one digest every morning.";

export const metadata: Metadata = {
  metadataBase: new URL("https://nightshift.dev"),
  title: "nightshift — your AI works the night shift",
  description,
  openGraph: {
    title: "nightshift",
    description,
    url: "https://nightshift.dev",
    siteName: "nightshift",
    type: "website",
  },
  twitter: { card: "summary_large_image", title: "nightshift", description },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${spaceGrotesk.variable} ${jetbrainsMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
