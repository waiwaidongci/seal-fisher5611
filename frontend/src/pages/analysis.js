import {store,load,currentStudy,currentKind} from '../stores/research.js';
import {runs} from '../api/research.js';
import {studySelect} from '../components/common/study-select.js';
import {runList} from '../components/common/run-list.js';
import {bindForm} from '../hooks/forms.js';
import {esc} from '../utils/format.js';
import {kindSpec} from '../constants/domain.js';
const labels={alpha:'显著性 α (0.001–0.2)',day:'指定日 (上架后天数)'};
export function render(){
  const writable=localStorage.getItem('research-role')!=='viewer';
  const spec=kindSpec(currentKind());
  return `<div class="eyebrow">02 / METHOD WORKSHEET</div><h1>${spec.field_label}</h1><p class="lead">${spec.algorithm}</p><div class="method-note">${spec.note}</div>${writable?`<form id="run-form" class="worksheet">${studySelect()}<label>本次研究名称<input name="name" required minlength="2" value="${esc(spec.names[0])} · 核算"></label><div class="inline-form">${Object.entries(spec.defaults).map(([key,value])=>`<label>${labels[key]||key}<input name="${key}" type="number" step="any" value="${value}" required></label>`).join('')}</div><p>提交时冻结全部观测与参数，生成 SHA256。后台 worker 独立执行；计算期间可以继续补录，补录只进入下一次运行。</p><button type="submit">冻结输入并排队计算 →</button></form>`:'<p class="method-note">观察员可阅读研究记录，分析师与负责人可以发起计算。</p>'}<h2>计算记录</h2>${runList()}`;
}
export function bind(refresh){
  const spec=kindSpec(currentKind());
  bindForm('run-form',async data=>{
    const parameters=Object.fromEntries(Object.keys(spec.defaults).map(k=>[k,+data[k]]));
    const r=await runs.create({study_id:+data.study_id,name:data.name,parameters});
    store.runId=r.id;await load();location.hash='results/'+r.id;
  });
  const sel=document.getElementById('study-select');
  if(sel)sel.onchange=()=>{store.studyId=+sel.value;refresh();};
}
