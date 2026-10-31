// Test driver for hass/tests/test_qa_env.py: prints qaEnv()'s result as JSON.
const {qaEnv}=require('../../../storefront-mockup/qa-env.cjs');
process.stdout.write(JSON.stringify(qaEnv({preview:true}))+'\n');
