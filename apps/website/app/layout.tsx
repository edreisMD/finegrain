import type { Metadata } from 'next';
import { Geist_Mono } from 'next/font/google';
import './globals.css';

const geistMono = Geist_Mono({ variable: '--font-geist-mono', subsets: ['latin'] });
export const metadata: Metadata = {
  title: 'GM Nightly Loop — company learning in weights',
  description: 'Part 2 of GM: approved company Gbrain knowledge becomes training data, evaluations, and a gated River fine-tune that starts from GM.',
  icons: { icon: '/coffee-bean.jpeg' },
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body className={`${geistMono.variable} antialiased`}>{children}</body></html>;
}
