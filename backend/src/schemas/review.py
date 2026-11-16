from pydantic import BaseModel, Field, field_validator
class ReviewInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    dataset_id: int
    indexes: list[int] | None = Field(default=None, max_length=5000)
    ttl_seconds: int = Field(default=86400, ge=60, le=2592000)
    @field_validator('indexes')
    @classmethod
    def indexes_valid(cls, v):
        if v is None: return v
        if not v: raise ValueError('观测序号不能为空')
        if any((not isinstance(i, int)) or isinstance(i, bool) or i < 0 for i in v): raise ValueError('观测序号须为非负整数')
        if len(set(v)) != len(v): raise ValueError('观测序号不得重复')
        return sorted(v)
class OpinionInput(BaseModel):
    decision: str = Field(pattern='^(keep|remove)$')
    rationale: str = Field(min_length=2, max_length=500)
