"""观测双盲复核：冻结批次、双人独立判定、盲态隔离、分歧裁决、超期改派与结案。"""
import copy, time
from fastapi import HTTPException
from sqlalchemy import select, update
from src.models import Dataset, Review, ReviewItem, ReviewAssignment, User
from src.utils.serialization import checksum

ACTIVE = ('open', 'submitted')

def _lock(db, model, pk):
    """行级写锁（占位 UPDATE）：Postgres 与 SQLite 下均阻塞并发写事务直至本事务提交，
    使领取、交卷、改派、结案的检查-写入序列原子化。"""
    db.execute(update(model).where(model.id == pk).values(id=pk))

def _review(db, review_id, lock=False):
    if lock: _lock(db, Review, review_id)
    r = db.get(Review, review_id)
    if not r: raise HTTPException(404, '复核批次不存在')
    return r

def _assignments(db, review_id):
    return list(db.scalars(select(ReviewAssignment).where(ReviewAssignment.review_id == review_id)))

def _items(db, review_id):
    return list(db.scalars(select(ReviewItem).where(ReviewItem.review_id == review_id).order_by(ReviewItem.id)))

def create(db, data, user):
    source = db.get(Dataset, data.dataset_id)
    if not source: raise HTTPException(404, '数据批次不存在')
    name = data.name.strip()
    if len(name) < 2: raise HTTPException(422, '复核名称去除空格后至少需要两个字符')
    if db.scalar(select(Review).where(Review.name == name)):
        raise HTTPException(409, '该复核批次名已存在，请修改名称')
    total = len(source.records)
    indexes = data.indexes if data.indexes is not None else list(range(total))
    if not indexes: raise HTTPException(422, '该数据批次没有可复核的观测')
    if max(indexes) >= total: raise HTTPException(422, f'观测序号超出范围：本批次共 {total} 条观测')
    frozen = copy.deepcopy(source.records)  # 发起时冻结批次，后续不受源数据改动影响
    r = Review(name=name, dataset_id=source.id, frozen_records=frozen, frozen_checksum=checksum(frozen),
               ttl_seconds=data.ttl_seconds, status='open', created_by=user.id, created_at=time.time())
    db.add(r); db.flush()
    for i in indexes:
        db.add(ReviewItem(review_id=r.id, idx=i, record=copy.deepcopy(frozen[i]), status='open'))
    db.flush()
    return r

def claim(db, review_id, user):
    r = _review(db, review_id, lock=True)
    if r.status != 'open': raise HTTPException(409, '该复核已结案，停止领件')
    all_assignments = _assignments(db, r.id)
    mine = {a.item_id for a in all_assignments if a.assignee_id == user.id and a.kind == 'review'}
    active = {}
    for a in all_assignments:
        if a.kind == 'review' and a.status in ACTIVE:
            active[a.item_id] = active.get(a.item_id, 0) + 1
    for item in _items(db, r.id):
        if item.status != 'open' or item.id in mine: continue
        if active.get(item.id, 0) >= 2: continue  # 每条观测至多两名不同复核员
        now = time.time()
        a = ReviewAssignment(review_id=r.id, item_id=item.id, kind='review', assignee_id=user.id,
                             status='open', claimed_at=now, due_at=now + r.ttl_seconds)
        db.add(a); db.flush()
        return a, item
    raise HTTPException(409, '暂无可领取的观测：均已领取、交卷或定案')

def claim_adjudication(db, review_id, user):
    r = _review(db, review_id, lock=True)
    if r.status != 'open': raise HTTPException(409, '该复核已结案，停止领取裁决')
    all_assignments = _assignments(db, r.id)
    involved = {a.item_id for a in all_assignments if a.assignee_id == user.id}  # 裁决员须未参与该条复核
    for item in _items(db, r.id):
        if item.status != 'disputed' or item.id in involved: continue
        if any(a.item_id == item.id and a.kind == 'adjudication' and a.status in ACTIVE for a in all_assignments):
            continue  # 每条分歧至多一名在办裁决员
        now = time.time()
        a = ReviewAssignment(review_id=r.id, item_id=item.id, kind='adjudication', assignee_id=user.id,
                             status='open', claimed_at=now, due_at=now + r.ttl_seconds)
        db.add(a); db.flush()
        pair = [x for x in all_assignments if x.item_id == item.id and x.kind == 'review' and x.status == 'submitted']
        return a, item, pair
    raise HTTPException(409, '暂无可裁决的分歧观测')

def submit(db, assignment_id, user, decision, rationale):
    _lock(db, ReviewAssignment, assignment_id)
    a = db.get(ReviewAssignment, assignment_id)
    if not a: raise HTTPException(404, '领取记录不存在')
    if a.assignee_id != user.id: raise HTTPException(403, '只能提交本人领取的任务')
    if a.status != 'open': raise HTTPException(409, '该领取已失效，晚到的意见不再受理')
    now = time.time()
    a.opinion = decision; a.rationale = rationale.strip(); a.status = 'submitted'; a.submitted_at = now
    _lock(db, ReviewItem, a.item_id)
    item = db.get(ReviewItem, a.item_id)
    if a.kind == 'review':
        pair = [x for x in db.scalars(select(ReviewAssignment).where(
            ReviewAssignment.item_id == item.id, ReviewAssignment.kind == 'review',
            ReviewAssignment.status == 'submitted'))]
        if len(pair) == 2:
            if pair[0].opinion == pair[1].opinion:
                item.final_decision = pair[0].opinion
                item.rationale = '双评一致：' + '；'.join(x.rationale for x in pair)
                item.status = 'resolved'; item.resolved_at = now
            else:
                item.status = 'disputed'  # 分歧待裁决
    else:
        item.final_decision = decision  # 裁决定案
        item.rationale = '裁决定案：' + a.rationale
        item.status = 'resolved'; item.resolved_at = now
    db.flush()
    return a, item

def reassign(db, assignment_id):
    _lock(db, ReviewAssignment, assignment_id)
    a = db.get(ReviewAssignment, assignment_id)
    if not a: raise HTTPException(404, '领取记录不存在')
    if a.status != 'open': raise HTTPException(409, '已交卷或已改派的领取不能再次改派')
    if time.time() <= a.due_at: raise HTTPException(409, '领取尚未超期，暂不能改派')
    a.status = 'revoked'; a.revoked_at = time.time()  # 旧领取作废，晚到意见将被拒绝；已交意见不受影响
    db.flush()
    return a

def close(db, review_id):
    r = _review(db, review_id, lock=True)
    if r.status == 'closed':  # 结案可重试：沿用原研究批次，不新增
        return r, db.get(Dataset, r.result_dataset_id)
    items = _items(db, r.id)
    pending = sum(1 for i in items if i.status != 'resolved')
    if pending: raise HTTPException(409, f'仍有 {pending} 条观测未齐或未裁决，不能结案')
    reviewed = {i.idx: i for i in items}
    records = []
    for pos, rec in enumerate(r.frozen_records):
        item = reviewed.get(pos)
        if item is None:
            records.append(copy.deepcopy(rec))  # 未列入复核的观测默认保留
        elif item.final_decision == 'keep':
            kept = copy.deepcopy(rec)
            kept['review_note'] = item.rationale  # 逐条依据随研究批次留存
            records.append(kept)
    name = '研究批次 · ' + r.name
    expected = checksum(records)
    dataset = db.scalar(select(Dataset).where(Dataset.name == name))
    if dataset and dataset.checksum != expected:
        raise HTTPException(409, '研究批次名称与既有数据批次冲突，请调整复核名称')
    if not dataset:
        dataset = Dataset(name=name, source=f'双盲复核 #{r.id}', records=records,
                          checksum=expected, created_at=time.time())
        db.add(dataset); db.flush()
    r.result_dataset_id = dataset.id; r.status = 'closed'; r.closed_at = time.time()
    db.flush()
    return r, dataset

def progress(db, review_id):
    items = _items(db, review_id)
    assignments = _assignments(db, review_id)
    now = time.time()
    submitted = {}
    for a in assignments:
        if a.kind == 'review' and a.status == 'submitted':
            submitted[a.item_id] = submitted.get(a.item_id, 0) + 1
    open_claims = [a for a in assignments if a.status == 'open']
    resolved = sum(1 for i in items if i.status == 'resolved')
    return {'total': len(items), 'resolved': resolved,
            'disputed': sum(1 for i in items if i.status == 'disputed'),
            'collecting': sum(1 for i in items if i.status == 'open' and submitted.get(i.id, 0) == 1),
            'waiting': sum(1 for i in items if i.status == 'open' and not submitted.get(i.id, 0)),
            'open_claims': len(open_claims),
            'overdue_claims': sum(1 for a in open_claims if a.due_at < now),
            'ready': bool(items) and resolved == len(items)}

def detail(db, review_id, user):
    r = _review(db, review_id)
    items = _items(db, r.id)
    assignments = _assignments(db, r.id)
    names = {u.id: u.name for u in db.scalars(select(User))}
    source = db.get(Dataset, r.dataset_id)
    base = {'id': r.id, 'name': r.name, 'status': r.status, 'dataset_id': r.dataset_id,
            'dataset_name': source.name if source else '源批次已删除', 'ttl_seconds': r.ttl_seconds,
            'frozen_rows': len(r.frozen_records), 'frozen_checksum': r.frozen_checksum,
            'result_dataset_id': r.result_dataset_id, 'created_at': r.created_at, 'closed_at': r.closed_at,
            'progress': progress(db, r.id)}
    def opinion_view(a, named):
        return {'decision': a.opinion, 'rationale': a.rationale, 'submitted_at': a.submitted_at,
                'reviewer': names.get(a.assignee_id, '未知') if named else None,
                'kind': a.kind}
    def pair_of(item_id):
        return [a for a in assignments if a.item_id == item_id and a.kind == 'review' and a.status == 'submitted']
    if user.role in ('admin', 'analyst'):
        idx_of = {i.id: i.idx for i in items}
        def full_item(i):
            pair = pair_of(i.id)
            adj = next((a for a in assignments if a.item_id == i.id and a.kind == 'adjudication' and a.status == 'submitted'), None)
            return {'id': i.id, 'idx': i.idx, 'record': i.record, 'status': i.status,
                    'final_decision': i.final_decision, 'rationale': i.rationale,
                    'opinions': [opinion_view(a, True) for a in pair],
                    'adjudication': opinion_view(adj, True) if adj else None}
        base['items'] = [full_item(i) for i in items]
        now = time.time()
        base['open_assignments'] = [
            {'id': a.id, 'item_id': a.item_id, 'idx': idx_of.get(a.item_id),
             'kind': a.kind, 'assignee': names.get(a.assignee_id, '未知'), 'claimed_at': a.claimed_at,
             'due_at': a.due_at, 'overdue': a.due_at < now}
            for a in assignments if a.status == 'open']
        base['revoked'] = [
            {'id': a.id, 'idx': idx_of.get(a.item_id), 'kind': a.kind,
             'assignee': names.get(a.assignee_id, '未知'), 'revoked_at': a.revoked_at}
            for a in assignments if a.status == 'revoked']
    elif user.role in ('reviewer', 'adjudicator'):
        kind = 'review' if user.role == 'reviewer' else 'adjudication'
        by_id = {i.id: i for i in items}
        mine = []
        for a in sorted((x for x in assignments if x.assignee_id == user.id and x.kind == kind), key=lambda x: x.id):
            item = by_id.get(a.item_id)
            entry = {'id': a.id, 'idx': item.idx if item else None, 'record': item.record if item else {},
                     'status': a.status, 'opinion': a.opinion, 'rationale': a.rationale,
                     'claimed_at': a.claimed_at, 'due_at': a.due_at, 'submitted_at': a.submitted_at,
                     'item_status': item.status if item else None}
            if a.kind == 'adjudication':  # 双方已交卷，盲态解除，裁决可见双方意见（匿名）
                entry['pair'] = [{'decision': x.opinion, 'rationale': x.rationale} for x in pair_of(a.item_id)]
            mine.append(entry)
        base['mine'] = mine
    if r.status == 'closed':
        named = user.role in ('admin', 'analyst')
        conclusions = []
        for i in items:
            pair = pair_of(i.id)
            adj = next((a for a in assignments if a.item_id == i.id and a.kind == 'adjudication' and a.status == 'submitted'), None)
            opinions = []
            for n, a in enumerate(pair):
                opinions.append({'who': names.get(a.assignee_id, '未知') if named else f'复核员{"一二"[n]}',
                                 'decision': a.opinion, 'rationale': a.rationale})
            if adj:
                opinions.append({'who': names.get(adj.assignee_id, '未知') if named else '裁决员',
                                 'decision': adj.opinion, 'rationale': adj.rationale})
            conclusions.append({'idx': i.idx, 'record': i.record, 'final_decision': i.final_decision,
                                'rationale': i.rationale, 'opinions': opinions})
        base['conclusions'] = conclusions
    return base
