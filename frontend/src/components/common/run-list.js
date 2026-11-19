import {store} from '../../stores/research.js';
import {table} from './table.js';
import {status} from './status.js';
import {esc} from '../../utils/format.js';
import {kindSpec} from '../../constants/domain.js';
export function runList(){return table(['编号 / 运行','研究类型','状态','源数据快照','复核'],store.runs.map(r=>[{html:`<a href="#results/${r.id}">#${r.id} ${esc(r.name)}</a>`},kindSpec(r.kind).label,{html:status(r.status)},r.snapshot_count+'条 · '+r.checksum.slice(0,12),r.review?'已复核':'待负责人复核']));}
