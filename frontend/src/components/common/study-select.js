import {store} from '../../stores/research.js';
import {esc} from '../../utils/format.js';
export const studySelect=()=>`<label>研究批次<select id="study-select" name="study_id">${store.studies.map(s=>`<option value="${s.id}" ${s.id===store.studyId?'selected':''}>${esc(s.name)} · ${esc(s.kind_label||'')} · ${s.row_count}条</option>`).join('')}</select></label>`;
