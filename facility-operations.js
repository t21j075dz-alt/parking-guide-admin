/* 施設の営業状態と重複区画の案内可否。端末のタイムゾーンに依存しない。 */
(function(root) {
  "use strict";
  function operating(operations = {}, now = new Date()) {
    operations = operations && typeof operations === "object" ? operations : {};
    const label=typeof operations.hoursLabel === "string"?operations.hoursLabel:"";
    if (operations.closed === true) return {closed:true,isOpen:false,preOpening:false,closingSoon:false,hours:label};
    const hours=operations.weeklyHours;
    if(!hours || typeof hours!=="object") return {closed:false,unknown:true,hours:label};
    let zone=operations.timeZone || "Asia/Tokyo";
    try {new Intl.DateTimeFormat("en-US",{timeZone:zone});} catch {zone="Asia/Tokyo";}
    const parts=new Intl.DateTimeFormat("en-US",{timeZone:zone,weekday:"short",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",second:"2-digit",hourCycle:"h23"}).formatToParts(now);
    const part=type=>parts.find(p=>p.type===type)?.value;
    const day=["Sun","Mon","Tue","Wed","Thu","Fri","Sat"].indexOf(part("weekday"));
    const minute=Number(part("hour"))*60+Number(part("minute"))+Number(part("second"))/60;
    const parse=t=>{if(!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(t))return NaN;const [h,m]=t.split(":").map(Number);return h*60+m;};
    const intervals=[];
    for(let offset=-7;offset<=7;offset++){
      const ranges=hours[String((day+offset+14)%7)];
      if(!Array.isArray(ranges))continue;
      for(const range of ranges){
        if(!Array.isArray(range)||range.length!==2)continue;
        const start=parse(range[0]),end=parse(range[1]);if(!Number.isFinite(start+end))continue;
        intervals.push({start:offset*1440+start,end:offset*1440+end+(end<=start?1440:0)});
      }
    }
    intervals.sort((a,b)=>a.start-b.start);
    const merged=[];
    for(const interval of intervals){const previous=merged.at(-1);if(previous&&interval.start<=previous.end)previous.end=Math.max(previous.end,interval.end);else merged.push({...interval});}
    const current=merged.find(i=>i.start<=minute&&minute<i.end);
    const next=merged.find(i=>i.start>minute);
    const preOpening=!current&&!!next&&next.start-minute<=60;
    const untilClose=current?current.end-minute:null;
    const today=hours[String(day)];
    const unknown=!Array.isArray(today)&&!current&&!preOpening;
    return {closed:!unknown&&!current&&!preOpening,isOpen:!!current,preOpening,unknown,
      openingInMinutes:preOpening?Math.ceil(next.start-minute):null,
      closingSoon:!!current&&untilClose<=60,
      closingInMinutes:current?Math.ceil(untilClose):null,
      closingKey:current?new Date(Date.UTC(Number(part("year")),Number(part("month"))-1,Number(part("day")))+current.end*60000).toISOString():null,
      hours:label||(Array.isArray(today)?today.filter(Array.isArray).map(r=>r.join("–")).join(" / "):"")};
  }
  function shared(spaces) {
    const blocked=new Set(spaces.filter(s=>s.isOccupied||s.occupancyStatus!=="available").map(s=>s.sourceObject?.sharedGroup).filter(Boolean));
    return spaces.map(s=>blocked.has(s.sourceObject?.sharedGroup)?{...s,isOccupied:true,occupancyStatus:s.occupancyStatus==="available"?"blocked":s.occupancyStatus}:s);
  }
  const api={operating,shared};
  if(typeof module!=="undefined") module.exports=api;
  else root.ParkingOperations=api;
})(typeof window!=="undefined"?window:globalThis);
