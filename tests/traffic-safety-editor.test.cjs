"use strict";
const {test}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");

function editor() {
  const controls=new Map();
  const messages=[];
  const layout={safetyAdvisories:[]};
  let trigger;
  function element() {
    return {
      value:"",checked:false,disabled:false,textContent:"",innerHTML:"",events:{},
      setAttribute(){},add(){},replaceChildren(){},showModal(){},close(){},
      addEventListener(name,cb){this.events[name]=cb;},
      querySelector(selector){return field(selector.slice(1));},
    };
  }
  function field(id) {
    if(!controls.has(id))controls.set(id,element());
    return controls.get(id);
  }
  const host={after(node){trigger=node;}};
  const document={
    querySelector(selector){return selector==="#camera-monitor"?host:null;},
    createElement(){return element();},
    body:{append(){}},
  };
  const sandbox={document, Option:class{constructor(label,value){this.label=label;this.value=value;}},
    getCurrentLayout:()=>layout,getAdminDestinations:()=>[],saveLocal:()=>messages.push("saved"),
    Date,Math,Array,Object,String,Boolean};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,"../traffic-safety-editor.js"),"utf8"),sandbox);
  trigger.events.click();
  return {field,layout,messages};
}

test("English safety messages are only approved through an explicit verified field",()=>{
  const {field,layout,messages}=editor();
  field("traffic-type").value="custom";
  field("traffic-message").value="西側入口をご利用ください。";
  field("traffic-message-en").value="Use the west entrance.";
  field("traffic-message-en-verified").checked=true;
  field("traffic-verified").checked=true;
  field("traffic-save").onclick();
  assert.equal(messages.length,1);
  assert.equal(layout.safetyAdvisories.length,1);
  assert.equal(layout.safetyAdvisories[0].messageEn,"Use the west entrance.");
  assert.equal(layout.safetyAdvisories[0].messageEnVerified,true);
  assert.equal(layout.safetyAdvisories[0].verified,true);
});
test("changing original traffic rule invalidates previously verified English translation",()=>{
  const {field,layout}=editor();
  field("traffic-message").value="右折入場は禁止です。";
  field("traffic-message-en").value="Right turns are prohibited.";
  field("traffic-message-en-verified").checked=true;
  field("traffic-save").onclick();
  assert.equal(layout.safetyAdvisories[0].messageEnVerified,true);
  field("traffic-message").value="右折入場は可能です。";
  field("traffic-message").events.input();
  assert.equal(field("traffic-message-en-verified").checked,false);
  field("traffic-save").onclick();
  const latest=layout.safetyAdvisories.at(-1);
  assert.equal(latest.messageEnVerified,false);
});
