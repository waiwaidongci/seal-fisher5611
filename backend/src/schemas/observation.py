from pydantic import BaseModel,Field
class TrialCountInput(BaseModel):
    source_key:str=Field(min_length=1,max_length=100)
    values:dict
ObservationInput=TrialCountInput

class TrialCountBatchItem(TrialCountInput):
    row_id:int|None=None

class TrialCountBatch(BaseModel):
    rows:list[TrialCountBatchItem]=Field(min_length=1,max_length=100000)
ObservationBatchInput=TrialCountBatch
