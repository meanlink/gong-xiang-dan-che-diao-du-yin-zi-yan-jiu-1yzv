import time, json
from sqlalchemy import select, func
from src.config.database import Session
from migrations.initial import migrate
from src.models import User, Dataset, Job, Report, Delivery, Audit, Review
from src.services.business import metadata, seed_records, analyze
from src.services.reports import deliver
from src.services import reviews as review_service
from src.schemas.review import ReviewInput
from src.utils.security import hash_password
from src.utils.serialization import checksum
def anomaly_indexes(rows, limit=12):
    """按站点需求量的 |z| 分数挑出最异常的观测序号，结果确定。"""
    groups = {}
    for i, row in enumerate(rows): groups.setdefault(row['station'], []).append((i, float(row['demand'])))
    scored = []
    for values in groups.values():
        mean = sum(v for _, v in values) / len(values)
        var = sum((v - mean) ** 2 for _, v in values) / len(values)
        std = var ** 0.5 or 1.0
        scored.extend((abs(v - mean) / std, i) for i, v in values)
    scored.sort(key=lambda x: (-x[0], x[1]))
    return sorted(i for _, i in scored[:limit])
def seed_review(db, dataset, admin):
    name = '11月异常客流双盲复核'
    if db.scalar(select(Review).where(Review.name == name)): return
    users = {u.email: u for u in db.scalars(select(User))}
    r1, r2, adj = users['reviewer1@demo.local'], users['reviewer2@demo.local'], users['adjudicator@demo.local']
    indexes = anomaly_indexes(dataset.records)
    review = review_service.create(db, ReviewInput(name=name, dataset_id=dataset.id, indexes=indexes, ttl_seconds=259200), admin)
    rounds = [('keep', 'keep', '客流显著偏离同时段基线，倾向保留观察', '剔除会抹平真实高峰信号'),
              ('remove', 'remove', '与相邻时段跳变过大，疑似录入异常', '同意，偏离幅度超出正常波动'),
              ('keep', 'remove', '通勤指数同步抬升，保留更稳妥', '需求跳变缺乏客流支撑，建议剔除')]
    # 前两条双评一致直接定案；第三条分歧由未参与复核的裁决员定案；第四条仅一人交卷仍在收集中
    for d1, d2, note1, note2 in rounds:
        a, _ = review_service.claim(db, review.id, r1); review_service.submit(db, a.id, r1, d1, note1)
        a, _ = review_service.claim(db, review.id, r2); review_service.submit(db, a.id, r2, d2, note2)
    a, _, _ = review_service.claim_adjudication(db, review.id, adj)
    review_service.submit(db, a.id, adj, 'keep', '客流与通勤同步抬升，剔除依据不足')
    a, _ = review_service.claim(db, review.id, r1)
    review_service.submit(db, a.id, r1, 'keep', '单时段突增但可解释，先保留')
def seed():
    migrate()
    with Session() as db:
        for email,role,name in [('admin@demo.local','admin','林知 · 业务负责人'),('analyst@demo.local','analyst','陈舟 · 分析员'),
                                ('viewer@demo.local','viewer','周禾 · 观察员'),('reviewer1@demo.local','reviewer','王谨 · 复核员一'),
                                ('reviewer2@demo.local','reviewer','李慎 · 复核员二'),('reviewer3@demo.local','reviewer','沈默 · 复核员三'),
                                ('adjudicator@demo.local','adjudicator','赵衡 · 裁决员一'),('adjudicator2@demo.local','adjudicator','钱允 · 裁决员二')]:
            if not db.scalar(select(User).where(User.email==email)):
                db.add(User(email=email,name=name,role=role,password=hash_password('Demo123!')))
        db.flush()
        m=metadata()
        d=db.scalar(select(Dataset).where(Dataset.name==m['dataset_name']))
        if not d:
            rows=seed_records()
            d=Dataset(name=m['dataset_name'],source=m['short']+'-202611.csv',records=rows,checksum=checksum(rows),created_at=time.time())
            db.add(d); db.flush()
        if not db.scalar(select(Job).where(Job.name=='基线复核 · '+m['name'])):
            params={p['key']:p['default'] for p in m.get('parameters',[])}
            result=analyze(d.records,params)
            json.dumps(result,ensure_ascii=False,allow_nan=False)
            admin=db.scalar(select(User).where(User.role=='admin'))
            j=Job(name='基线复核 · '+m['name'],dataset_id=d.id,params=params,status='completed',result=result,created_by=admin.id,created_at=time.time()-3600,finished_at=time.time()-3595,approved=True)
            db.add(j);db.flush()
            r=Report(name='每日业务复核简报',job_id=j.id,destination='业务复核组 · 本地收件箱',interval_seconds=86400,next_run=time.time()+86400,enabled=True)
            db.add(r);db.flush();deliver(db,r)
            db.add(Audit(actor='seed',action='demo.baseline',detail={'dataset':d.id},at=time.time()))
        admin=db.scalar(select(User).where(User.role=='admin'))
        seed_review(db, d, admin)
        db.commit()
        counts={model.__tablename__:db.scalar(select(func.count()).select_from(model)) for model in [User,Dataset,Job,Report,Delivery,Audit,Review]}
        print(json.dumps(counts,ensure_ascii=False))
        return counts
if __name__=='__main__':seed()
