import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Header } from "@/components/ui/Header";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "fin-aily-us — AI Stock News Insights",
  description: "Get AI-powered summaries of the latest news for US-listed companies.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${inter.className} bg-white text-slate-900 antialiased`}>
        <Header />
        <main className="mx-auto max-w-3xl px-4 py-8">
          {children}
        </main>
      </body>
    </html>
  );
}
