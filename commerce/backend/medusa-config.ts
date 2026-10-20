import { defineConfig, loadEnv } from '@medusajs/framework/utils'
loadEnv(process.env.NODE_ENV || 'development', process.cwd())
module.exports = defineConfig({
  admin: { disable: true },
  projectConfig: {
    databaseUrl: process.env.DATABASE_URL,
    http: {
      storeCors: 'http://127.0.0.1:3100,http://localhost:3100',
      adminCors: 'http://127.0.0.1:3100',
      authCors: 'http://127.0.0.1:3100',
      jwtSecret: process.env.JWT_SECRET!, cookieSecret: process.env.COOKIE_SECRET!,
    },
  },
  modules: [{resolve:'@medusajs/medusa/payment',options:{providers:[{resolve:'./src/providers/hosted-checkout/index.ts',id:'hosted',options:{apiKey:process.env.STRIPE_SECRET_KEY,webhookSecret:process.env.STRIPE_WEBHOOK_SECRET,mode:process.env.PAYMENT_MODE || 'simulator',storeUrl:'http://127.0.0.1:3100'}}]}}],
})
