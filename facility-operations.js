/* 施設の営業状態と重複区画の案内可否。端末のタイムゾーンに依存しない。 */
(function(root) {
  "use strict";
  function operating(operations = {}, now = new Date()) {
    operations = operations && typeof operations === "object" ? operations : {};
    const label=typeof operations.hoursLabel === "string"?operations.hoursLabel:"";
    // 明示的な休業指定は休業日扱い。営業時間外「閉」と区別する。
    if (operations.closed === true) return {closed:true,closureKind:"rest",isOpen:false,preOpening:false,closingSoon:false,hours:label,closedReason:"manual"};
    let zone=operations.timeZone || "Asia/Tokyo";
    try {new Intl.DateTimeFormat("en-US",{timeZone:zone});} catch {zone="Asia/Tokyo";}
    const parts=new Intl.DateTimeFormat("en-US",{timeZone:zone,weekday:"short",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",second:"2-digit",hourCycle:"h23"}).formatToParts(now);
    const part=type=>parts.find(p=>p.type===type)?.value;
    // 元日など、毎年同じ日付に休業する店舗の例外。曜日の営業時間より優先する。
    const dateKey=`${part("month")}-${part("day")}`;
    if(Array.isArray(operations.annualClosedDates) && operations.annualClosedDates.includes(dateKey)) {
      return {closed:true,closureKind:"rest",isOpen:false,preOpening:false,closingSoon:false,hours:label,closedReason:"annual"};
    }
    // 棚卸・改装など日時を指定した臨時休業。ISO 8601（+09:00付き）で登録する。
    const temporaryClosure=Array.isArray(operations.specialClosures)
      ? operations.specialClosures.find(item => {
          const start=Date.parse(item?.start || ""),end=Date.parse(item?.end || "");
          return Number.isFinite(start)&&Number.isFinite(end)&&start<=now.getTime()&&now.getTime()<end;
        }) : null;
    if(temporaryClosure) {
      return {closed:true,closureKind:"rest",isOpen:false,preOpening:false,closingSoon:false,hours:label,
        closedReason:temporaryClosure.reason || "temporary"};
    }
    const hours=operations.weeklyHours;
    if(!hours || typeof hours!=="object") return {closed:false,unknown:true,hours:label};
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
    const today=hours[String(day)];
    // 休業日でも前夜からの深夜営業が続く間は営業中。終了後は「休」。
    const restDay=Array.isArray(today)&&today.length===0&&!current;
    // 開店60分前は従来どおり案内可能。ただし画面の状態表示は「閉」。
    const preOpening=!restDay&&!current&&!!next&&next.start-minute<=60;
    const untilClose=current?current.end-minute:null;
    const unknown=!Array.isArray(today)&&!current&&!preOpening;
    const closed=!unknown&&!current&&!preOpening;
    return {closed,closureKind:restDay?"rest":closed?"closed":null,isOpen:!!current,preOpening,unknown,
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
