import { describe,it,expect } from 'vitest';
import { seriesKey, type Odds } from './api';
describe('odds series boundaries',()=>{it('keeps provider, company, market, selection and line independent',()=>{
 const quote={provider:'a',bookmaker:'Pinnacle',market_type:'ASIAN_HANDICAP',selection:'HOME',line:'-0.75'} as Odds;
 const variants=[{...quote,line:'-1'},{...quote,provider:'b'},{...quote,selection:'AWAY'},{...quote,bookmaker:'Bet365'}];
 expect(new Set([seriesKey(quote),...variants.map(seriesKey)]).size).toBe(5);
})});
