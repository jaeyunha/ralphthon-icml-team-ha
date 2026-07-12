import type { Metadata } from "next";
import type { ReactNode } from "react";
import { SiteHeader } from "@/components/viewer-shell";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Ralph Review Viewer", template: "%s · Ralph Review" },
  description: "Read-only ICML-style peer review run viewer",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <SiteHeader />
        {children}
        <footer className="site-footer">
          <div><strong>Ralph Review</strong><span>Experimental ICML-style simulator · not an official peer-review system</span></div>
          <span>Validated published artifacts only</span>
        </footer>
      </body>
    </html>
  );
}
