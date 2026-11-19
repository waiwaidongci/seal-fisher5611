import {store} from '../stores/research.js';
import {runs} from '../api/research.js';
import {esc,fmt} from '../utils/format.js';
import {table} from '../components/common/table.js';
import {status} from '../components/common/status.js';
import {runList} from '../components/common/run-list.js';
import {download} from '../utils/download.js';
import {kindSpec} from '../constants/domain.js';

function riskSummary(r){
  const m=r.result.metrics||{};
  const diff=m['B减A漏封风险差'];
  return `<div class="strip"><span><strong>B减A 漏封风险差 ${diff>0?'+':''}${fmt(diff)}</strong></span><span>A组在险 ${fmt(m['A组指定日在险试件'])} 件</span><span>B组在险 ${fmt(m['B组指定日在险试件'])} 件</span><span>总试件 ${fmt(m['总试件数'])} 件 · 第 ${fmt(m['指定日 (天)'])} 天</span></div>`;
}

export async function render(id){
  if(!id)return `<h1>计算结果与解释</h1><p>选择一次运行查看冻结输入、算法结果与业务解释。</p>${runList()}`;
  const r=await runs.get(id);store.runId=r.id;
  const shelf=r.kind==='shelf_risk';
  const refused=(r.error||'').startsWith('拒绝出结论');
  const failed=r.status==='failed'
    ?`<div class="error"><strong>${refused?'':'计算失败：'}</strong>${esc(r.error)}${/。$/.test(r.error||'')?'':'。'}${refused?'请核对指定日或在险观察后重新冻结运行。':'请到来源页修复数据，然后创建新运行。'}</div>`
    :null;
  const body=r.result?`${shelf?riskSummary(r):''}<section class="result-intro"><strong>${esc(r.result.interpretation)}</strong><p>${esc(r.result.caveat)}</p></section><h2>核心数值</h2>${table(['业务指标','计算值'],Object.entries(r.result.metrics).map(([k,v])=>[k,fmt(v)]))}<h2>${esc(r.result.table_title||'计算明细')}</h2>${table(r.result.columns,r.result.rows)}${r.result.assumptions?`<h2>方法与假设</h2><ul>${r.result.assumptions.map(a=>`<li>${esc(a)}</li>`).join('')}</ul>`:''}${r.result.chart?`<h2>${esc(r.result.chart.title)}</h2><div class="chart">${r.result.chart.points.map(([x,y])=>`<div class="chart-row"><span>${esc(fmt(x))}</span><i style="width:${Math.max(1,Math.min(100,Number(y)*100))}%"></i><b>${esc(fmt(y))}</b></div>`).join('')}</div>`:''}<div class="toolbar"><button id="export">下载核算 CSV</button><a class="button secondary" href="#review/${r.id}">打开业务复核 →</a></div>`:'<p class="method-note">任务正在队列中。此页每2秒更新，结果写入数据库后展示。</p>';
  return `<div class="eyebrow">03 / RESULTS ARCHIVE · RUN ${r.id}</div><h1>${esc(r.name)} ${status(r.status)}</h1><div class="checksum">INPUT SHA256 ${r.checksum}</div><p>快照 ${r.snapshot.length} 条 · ${esc(r.created_at)} · ${r.review?'负责人已复核':'尚未复核'} · 研究类型 ${esc(kindSpec(r.kind).label)}</p>${failed||body}<details><summary>本次冻结的参数与源记录</summary><pre>${esc(JSON.stringify({parameters:r.parameters,snapshot:r.snapshot},null,2))}</pre></details>`;
}
export function bind(){
  const button=document.getElementById('export');
  if(button)button.onclick=async()=>{try{download(await runs.export(store.runId),'research-'+store.runId+'.csv');}catch(e){document.getElementById('notice').textContent=e.message;}};
}
