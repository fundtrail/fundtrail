import type { Metadata } from "next";
import { Bricolage_Grotesque, Geist, Geist_Mono, Newsreader } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

// The design system's families, served by Next.js. Each one sets a CSS variable
// on <html>, and globals.css builds --sans, --mono, --serif and --display on them.
const geist = Geist({ subsets: ["latin"], variable: "--font-geist", display: "swap" });
const geistMono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono", display: "swap" });
const newsreader = Newsreader({ subsets: ["latin"], variable: "--font-newsreader", display: "swap", axes: ["opsz"] });
const bricolage = Bricolage_Grotesque({
  subsets: ["latin"],
  variable: "--font-bricolage",
  display: "swap",
  weight: ["500", "600", "700", "800"],
});

export const metadata: Metadata = {
  title: "FundTrail",
  description: "A running evidence file for every research grant.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geist.variable} ${geistMono.variable} ${newsreader.variable} ${bricolage.variable}`}>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
