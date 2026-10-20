import {ModuleProvider,Modules} from '@medusajs/framework/utils'
import HostedCheckoutProvider from './service.ts'
export default ModuleProvider(Modules.PAYMENT,{services:[HostedCheckoutProvider]})
