import type { Metadata } from 'next';
import { Geist_Mono } from 'next/font/google';
import './globals.css';

const geistMono = Geist_Mono({ variable: '--font-geist-mono', subsets: ['latin'] });
export const metadata: Metadata = {
  title: 'GM — your company’s learning loop',
  description: 'An open-source framework that turns approved company Gbrain knowledge into training data, evaluations, and a company model fine-tuned through River.',
  icons: { icon: '/gm-mark.svg' },
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body className={`${geistMono.variable} antialiased`}>{children}</body></html>;
}
