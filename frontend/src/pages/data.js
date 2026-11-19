import {store,load,loadRows,currentKind} from '../stores/research.js';
import {studies} from '../api/research.js';
import {studySelect} from '../components/common/study-select.js';
import {table} from '../components/common/table.js';
import {esc} from '../utils/format.js';
import {bindForm} from '../hooks/forms.js';
import {KINDS,DEFAULT_KIND,kindSpec,isShelf} from '../constants/domain.js';

function fieldInput(field,value){
  const [key,label,kind]=field;
  const optional=field[3]==='optional';
  return `<label>${esc(label)}${optional?' <small>可选</small>':''}<input name="${key}" type="${kind}" ${kind==='number'?'step="any" min="0"':''} value="${optional&&value==null?'':esc(value??'')}" ${optional?'':'required'}></label>`;
}

export function outcomeText(values){
  if(values.leak!=null)return `漏封 @ 第 ${values.leak} 天`;
  if(values.break!=null)return `破包 @ 第 ${values.break} 天`;
  if(values.loss!=null)return `失访 @ 第 ${values.loss} 天`;
  return '在观察';
}

export async function render(){
  await loadRows();
  const kind=currentKind(),spec=kindSpec(kind),shelf=isShelf(kind);
  const writable=localStorage.getItem('research-role')!=='viewer';
  const fields=spec.fields;
  const headers=['源记录',...fields.map(f=>f[1]),...(shelf?['首次结局']:[]),...(writable?['操作']:[])];
  const rows=store.rows.map(row=>{
    const values=fields.map(f=>row.values[f[0]]??'—');
    const outcome=shelf?[outcomeText(row.values)]:[];
    return [row.source_key,...values,...outcome,...(writable?[{html:`<button class="text" data-edit="${row.id}">编辑</button> <button class="text" data-delete="${row.id}">移除</button>`}]:[])];
  });
  return `<div class="eyebrow">01 / SOURCE REGISTER</div><h1>${spec.study_label}与${spec.row_label}</h1><p>${spec.note}</p><div class="toolbar">${studySelect()}</div>${writable?`<details><summary>新增${spec.study_label}（研究类型）</summary><form id="study-form" class="inline-form"><label>名称<input name="name" required minlength="2"></label><label>研究类型<select name="kind">${Object.entries(KINDS).map(([k,v])=>`<option value="${k}" ${k===DEFAULT_KIND?'selected':''}>${esc(v.label)}</option>`).join('')}</select></label><label>来源文件<input name="source_filename" value="field-notes-202611.csv" required></label><label>说明<input name="description"></label><button type="submit">保存批次</button></form></details><h2 id="row-heading">录入${spec.row_label}</h2><form id="row-form" class="inline-form"><label>源记录编号<input name="source_key" placeholder="如 FIELD-001" required></label>${fields.map(f=>fieldInput(f,'')).join('')}<button type="submit">保存观测</button><button type="button" id="stage-row">暂存到整批更正</button><button type="button" id="cancel-edit" hidden>取消编辑</button></form><div class="method-note"><strong>整批更正</strong><p id="batch-note">暂存 0 行。</p><p>一次更正若同时涉及A与B，先把各行“暂存”，再整批提交；整批在一个事务内生效，并发开跑只会取到更正前或更正后的完整输入。</p><button type="button" id="batch-submit" disabled>提交整批更正</button> <button type="button" class="text" id="batch-clear" hidden>清空暂存</button></div>`:''}<h2>观测明细 <small>${store.rows.length} 条 · 运行后更改不会改写历史快照</small></h2>${table(headers,rows)}`;
}

const staged=new Map();
export function bind(refresh){
  let editing=null;
  const spec=kindSpec(currentKind()),fields=spec.fields;
  const sel=document.getElementById('study-select');
  if(sel)sel.onchange=()=>{store.studyId=+sel.value;staged.clear();refresh();};
  bindForm('study-form',async data=>{const s=await studies.create(data);store.studyId=s.id;await load();refresh();});
  const form=()=>document.getElementById('row-form');
  const readValues=()=>{
    const values={},f=form();
    fields.forEach(([key,,kind])=>{const raw=(f.elements[key].value||'').trim();values[key]=kind==='number'?(raw===''?null:+raw):raw;});
    return values;
  };
  const payload=()=>({source_key:form().elements.source_key.value.trim(),row_id:editing?.id??null,values:readValues()});
  const saveOne=async()=>{
    try{await studies.saveBatch(store.studyId,[payload()]);staged.delete(form().elements.source_key.value.trim());editing=null;await load();refresh();}
    catch(e){document.getElementById('notice').textContent=e.message;}
  };
  bindForm('row-form',saveOne);
  const stage=document.getElementById('stage-row');
  if(stage)stage.onclick=()=>{
    const p=payload();
    if(!p.source_key){document.getElementById('notice').textContent='先填写源记录编号';return;}
    staged.set(p.source_key,{row_id:p.row_id,values:p.values});
    editing=null;refresh();
  };
  document.querySelectorAll('[data-edit]').forEach(el=>el.onclick=()=>{
    const row=store.rows.find(r=>r.id===+el.dataset.edit),f=form();
    editing={id:row.id};
    f.elements.source_key.value=row.source_key;
    fields.forEach(([key])=>f.elements[key].value=row.values[key]??'');
    document.getElementById('row-heading').textContent='编辑 '+row.source_key;
    document.getElementById('cancel-edit').hidden=false;
    f.scrollIntoView({behavior:'smooth',block:'center'});
  });
  const cancel=document.getElementById('cancel-edit');
  if(cancel)cancel.onclick=()=>{editing=null;refresh();};
  document.querySelectorAll('[data-delete]').forEach(el=>el.onclick=async()=>{
    try{await studies.remove(store.studyId,+el.dataset.delete);staged.delete(store.rows.find(r=>r.id===+el.dataset.delete)?.source_key);await load();refresh();}
    catch(e){document.getElementById('notice').textContent=e.message;}
  });
  const note=document.getElementById('batch-note'),submit=document.getElementById('batch-submit'),clear=document.getElementById('batch-clear');
  const paint=()=>{
    if(!note)return;
    const n=staged.size;
    note.textContent=n?`暂存 ${n} 行：${[...staged.keys()].join('、')}`:'暂存 0 行。';
    if(submit)submit.disabled=!n;
    if(clear)clear.hidden=!n;
  };
  paint();
  if(submit)submit.onclick=async()=>{
    try{await studies.saveBatch(store.studyId,[...staged.entries()].map(([source_key,x])=>({source_key,row_id:x.row_id,values:x.values})));staged.clear();await load();refresh();}
    catch(e){document.getElementById('notice').textContent=e.message;}
  };
  if(clear)clear.onclick=()=>{staged.clear();refresh();};
}
