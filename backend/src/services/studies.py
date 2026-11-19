from fastapi import HTTPException
from sqlalchemy import select,func
from src.models.study import Study
from src.models.observation import Observation
from src.services.domain_validation import (
    MAX_SPECIMENS,
    DEFAULT_KIND,
    kind_spec,
    validate_values,
)
from src.services.audits import log
from src.utils.serializers import record


def list_studies(db):
    data=[]
    for s in db.scalars(select(Study).order_by(Study.id)):
        x=record(s);x['kind']=x.get('kind') or DEFAULT_KIND
        x['kind_label']=kind_spec(x['kind'])['label']
        x['row_count']=db.scalar(select(func.count()).select_from(Observation).where(Observation.study_id==s.id))
        data.append(x)
    return data

def create(db,data,user):
    if db.scalar(select(Study).where(Study.name==data.name)): raise HTTPException(409,'批次名称已存在')
    try: kind_spec(data.kind)
    except ValueError as e: raise HTTPException(422,str(e))
    s=Study(**data.model_dump());db.add(s);log(db,user,'study.create',data.name);db.commit();return record(s)

def require(db,id):
    s=db.get(Study,id)
    if not s: raise HTTPException(404,'业务批次不存在')
    return s

def study_kind(s):
    return getattr(s,'kind',None) or DEFAULT_KIND

def observations(db,id):
    require(db,id)
    return [record(x) for x in db.scalars(select(Observation).where(Observation.study_id==id).order_by(Observation.id))]

def max_rows(kind):
    return MAX_SPECIMENS if kind=='shelf_risk' else 5000

def _validate(study,values):
    try: return validate_values(values,study_kind(study))
    except (ValueError,TypeError) as e: raise HTTPException(422,str(e))

def _duplicate(db,study_id,source_key,row_id=None):
    other=db.scalar(select(Observation).where(Observation.study_id==study_id,Observation.source_key==source_key))
    if other and other.id!=row_id: raise HTTPException(409,'源记录编号重复')

def save_observation(db,id,data,user,row_id=None):
    study=require(db,id)
    values=_validate(study,data.values)
    _duplicate(db,id,data.source_key,row_id)
    if row_id:
        row=db.get(Observation,row_id)
        if not row or row.study_id!=id: raise HTTPException(404,'记录不存在')
        row.source_key=data.source_key;row.values=values
    else:
        if db.scalar(select(func.count()).select_from(Observation).where(Observation.study_id==id))>=max_rows(study_kind(study)):
            raise HTTPException(422,'该研究最多'+str(max_rows(study_kind(study)))+'行')
        row=Observation(study_id=id,source_key=data.source_key,values=values);db.add(row)
    log(db,user,'observation.save',f'{id}/{data.source_key}');db.commit();return record(row)

def save_observations_batch(db,id,rows,user):
    """Apply a correction touching several specimens as one transaction.

    Existing rows are addressed by row_id; a correction resubmits each
    specimen's own id, so source_key duplication is still refused instead of
    being silently merged.  Items without a row_id add new specimens.  A run
    snapshot taken concurrently sees either the whole batch before the commit
    or the whole batch after it, never a half-corrected group pair.
    """
    study=require(db,id)
    if not rows: raise HTTPException(422,'批量更正至少包含一条记录')
    prepared=[]
    seen_keys=set()
    seen_ids=set()
    for item in rows:
        if item.source_key in seen_keys: raise HTTPException(422,'批量更正内源记录编号重复')
        seen_keys.add(item.source_key)
        if item.row_id is not None:
            if item.row_id in seen_ids: raise HTTPException(422,'批量更正内记录重复')
            seen_ids.add(item.row_id)
        prepared.append((item.source_key,_validate(study,item.values),item.row_id))
    for source_key,_,row_id in prepared:
        _duplicate(db,id,source_key,row_id)
    total=db.scalar(select(func.count()).select_from(Observation).where(Observation.study_id==id))
    added=sum(1 for _,_,row_id in prepared if row_id is None)
    if total+added>max_rows(study_kind(study)):
        raise HTTPException(422,'该研究最多'+str(max_rows(study_kind(study)))+'行')
    resolved=[]
    for source_key,values,row_id in prepared:
        if row_id is not None:
            row=db.get(Observation,row_id)
            if not row or row.study_id!=id: raise HTTPException(404,'记录不存在')
        else:
            row=Observation(study_id=id,source_key=source_key,values=values);db.add(row)
        row.source_key=source_key;row.values=values
        resolved.append(row)
    # One commit for the whole correction: all A and B changes land together.
    db.flush()
    log(db,user,'observation.batch',f'{id}/{len(resolved)} rows')
    db.commit()
    return [record(x) for x in resolved]
