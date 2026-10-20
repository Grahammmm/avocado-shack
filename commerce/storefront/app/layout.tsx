import './globals.css';
import type { Metadata } from 'next';
export const metadata:Metadata={title:'Avocado Shack | Your neighborhood market in Morro Bay',description:'Good food, close to home. Shop Avocado Shack for local pickup in Morro Bay.',robots:{index:false,follow:false}};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}</body></html>}
