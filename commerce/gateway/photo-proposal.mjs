const kinds=['single_candidate','multiple_candidates','context','unknown'];
export function photoProposal(input){
 if(!input||typeof input!=='object'||!kinds.includes(input.kind))return undefined;
 const candidates=Array.isArray(input.candidates)?[...new Set(input.candidates.filter(s=>typeof s==='string'&&s.trim()&&s.length<=160&&!/^(?:unknown|unclear|unidentified|n\/a)$/i.test(s.trim())).map(s=>s.trim()))].slice(0,48):[];
 const kind=input.kind==='single_candidate'&&candidates.length!==1?'unknown':input.kind;
 return {kind,candidates:kind==='context'?[]:candidates,basis:'Local Qwen visual proposal; identity suggestions require owner review',unknowns:['selling unit/package','owner price','online quantity','stock action','handling/tax review'],claims_not_inferred:true,automatic:input.automatic!==false};
}

export function combinePhotoProposals(input){
 const reviews=input.map(photoProposal).filter(Boolean);if(!reviews.length||reviews.length>6)return undefined;if(reviews.length===1)return reviews[0];
 const candidates=[...new Set(reviews.flatMap(p=>p.kind==='context'?[]:p.candidates))].slice(0,48);
 const kind=reviews.every(p=>p.kind==='context')?'context':!candidates.length?'unknown':reviews.every(p=>p.kind==='single_candidate')&&candidates.length===1?'single_candidate':'multiple_candidates';
 return photoProposal({kind,candidates});
}
