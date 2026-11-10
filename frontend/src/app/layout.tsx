import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FundTrail",
  description: "A running evidence file for every research grant.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
