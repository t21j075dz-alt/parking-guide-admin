// SVGと実際のレンダラーを通信なしで検証する最小DOM。
function element(tag='div') {
  const node={tagName:tag,children:[],attributes:{},dataset:{},value:'',checked:false,hidden:false,clientWidth:360,clientHeight:400,options:[],
    style:{setProperty(key,value){this[key]=value;},removeProperty(key){delete this[key];}},
    append(...children){this.children.push(...children);},replaceChildren(...children){this.children=children;this._text='';},
    setAttribute(key,value){this.attributes[key]=String(value);if(key==='class')this.className=value;},getAttribute(key){return this.attributes[key]??null;},removeAttribute(key){delete this.attributes[key];},
    addEventListener(){},focus(){},reset(){},setCustomValidity(value){this.validationMessage=value;},reportValidity(){},
    querySelector(selector){return walk(this).slice(1).find(n=>selector.startsWith('.')?String(n.className||'').split(/\s+/).includes(selector.slice(1)):selector.includes('data-uid=')?n.dataset.uid===selector.match(/data-uid="([^"]+)"/)?.[1]:false)??null;},querySelectorAll(){return [];}
  };
  Object.defineProperty(node,'textContent',{get(){return (this._text||'')+this.children.map(c=>c.textContent||'').join('');},set(v){this._text=String(v);this.children=[];}});
  node.classList={add(...classes){node.className=[...new Set([...String(node.className||'').split(/\s+/),...classes])].join(' ').trim();},toggle(name,enabled){const list=new Set(String(node.className||'').split(/\s+/));if(enabled??!list.has(name))list.add(name);else list.delete(name);node.className=[...list].join(' ');},contains(name){return String(node.className||'').split(/\s+/).includes(name);}};
  return node;
}
function walk(node){return [node,...(node.children??[]).flatMap(walk)];}
module.exports={element,walk};
