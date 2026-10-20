const fail=message=>Object.assign(new Error(message),{status:422});
export function discountRule(baseMinor,text){
 if(!Number.isSafeInteger(baseMinor)||baseMinor<=0)throw fail('A confirmed regular price is required.');const value=text.trim();let rule,amount;
 const fixed=value.match(/^\$(\d+)(?:\.(\d{1,2}))?$/),percent=value.match(/^(\d{1,3})(?:\.(\d{1,2}))?%\s+off$/i);
 if(fixed){amount=BigInt(fixed[1])*100n+BigInt((fixed[2]||'').padEnd(2,'0')||'0');rule={type:'fixed',expression:value};}
 else if(percent){const basisPoints=Number(percent[1])*100+Number((percent[2]||'').padEnd(2,'0')||0);if(basisPoints<=0||basisPoints>=10000)throw fail('Use a percentage greater than zero and less than 100.');amount=(BigInt(baseMinor)*BigInt(10000-basisPoints)+5000n)/10000n;rule={type:'percentage',basis_points:basisPoints,expression:value,rounding:'nearest cent per selling unit; half cents round up'};}
 else throw fail('Specify a lower dollar price or an exact percentage, such as 25% off.');
 if(amount<=0n||amount>=BigInt(baseMinor)||amount>BigInt(Number.MAX_SAFE_INTEGER))throw fail('The resolved special must have a lower positive price.');return {price_minor:Number(amount),rule};
}
