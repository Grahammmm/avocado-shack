import {utcFromLocal} from './pickup-time.mjs';
const bad=()=>Object.assign(new Error('Use an exact date and time, such as 2026-10-06 9am (local time), or an ISO timestamp with offset.'),{status:422});
export function offerTime(text){const s=text.trim(),day=s.slice(0,10);if(!/^\d{4}-\d{2}-\d{2}$/.test(day)||!Number.isFinite(Date.parse(day+'T12:00:00Z'))||new Date(day+'T12:00:00Z').toISOString().slice(0,10)!==day)throw bad();
 if(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})$/.test(s)&&Number.isFinite(Date.parse(s)))return new Date(s).toISOString();
 const m=s.match(/^\d{4}-\d{2}-\d{2}\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$/i);if(!m)throw bad();let hour=Number(m[1]),minute=Number(m[2]||0);if(minute>59||hour>(m[3]?12:23)||m[3]&&hour<1||!m[3]&&!m[2])throw bad();if(m[3])hour=hour%12+(m[3].toLowerCase()==='pm'?12:0);
 const result=new Date(utcFromLocal(day,hour).getTime()+minute*60000),matches=date=>{const p=Object.fromEntries(new Intl.DateTimeFormat('en-US',{timeZone:'America/Los_Angeles',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(date).map(p=>[p.type,p.value]));return `${p.year}-${p.month}-${p.day}`===day&&Number(p.hour)===hour&&Number(p.minute)===minute};
 if(!matches(result)||matches(new Date(result.getTime()-3600000))||matches(new Date(result.getTime()+3600000)))throw Object.assign(new Error('That local time is missing or repeats during daylight saving. Use an ISO timestamp with an explicit offset.'),{status:422});return result.toISOString();
}
