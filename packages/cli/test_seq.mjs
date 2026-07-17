import fs from 'fs';
const csv = fs.readFileSync('/Users/shigehiro/gakumas-workspace/gakumas-support_cards/support_cards.csv', 'utf8');
const lines = csv.split('\n').slice(1).filter(l => l.trim());
const ids = lines.map(l => l.split(',')[2]);
const ssr = ids.filter(i => i.startsWith('SP_SSR_')).map(i => parseInt(i.split('_')[2])).sort((a,b)=>a-b);
const sr = ids.filter(i => i.startsWith('SP_SR_')).map(i => parseInt(i.split('_')[2])).sort((a,b)=>a-b);
const r = ids.filter(i => i.startsWith('SP_R_')).map(i => parseInt(i.split('_')[2])).sort((a,b)=>a-b);

function findMissing(arr, prefix) {
   if (arr.length === 0) return;
   const min = arr[0], max = arr[arr.length-1];
   for(let i=1; i<=max; i++) {
      if (!arr.includes(i)) console.log("Missing " + prefix + i.toString().padStart(4, '0'));
   }
}
findMissing(ssr, 'SP_SSR_');
findMissing(sr, 'SP_SR_');
findMissing(r, 'SP_R_');
