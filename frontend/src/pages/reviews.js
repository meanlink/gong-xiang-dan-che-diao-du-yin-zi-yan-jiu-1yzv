import {reviews,datasets} from '../api/entities.js';
import {workspace} from '../stores/workspace.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {table} from '../components/common/table.js';
import {ReviewStatus,ItemStatus,Decision} from '../constants/enums.js';
import {esc,fmt,date,notify} from '../utils/dom.js';
import {submit} from '../hooks/forms.js';
const recOf=r=>workspace.meta.columns.map(c=>esc(c.label)+' '+esc(fmt(r?.[c.key]))).join(' · ');
function opinionForm(a,actionLabel){
 return '<form class="opinion-form" data-assignment="'+a.id+'"><div class="record-line">第 '+(a.idx+1)+' 行 · '+recOf(a.record)+'</div>'
  +(a.pair?'<div class="pair-box"><p class="eyebrow">双方已交卷 · 匿名</p>'+a.pair.map((p,i)=>'<p>复核员'+'一二'[i]+'：'+esc(Decision[p.decision]||p.decision)+' — '+esc(p.rationale)+'</p>').join('')+'</div>':'')
  +'<div class="decision-row"><label class="radio"><input type="radio" name="decision" value="keep" required> 保留</label><label class="radio"><input type="radio" name="decision" value="remove"> 剔除</label></div>'
  +'<label>判定依据<textarea name="rationale" rows="2" required minlength="2" maxlength="500" placeholder="写下可复核的判定依据"></textarea></label>'
  +'<button type="submit" class="primary">'+esc(actionLabel)+'</button><small>到期 '+date(a.due_at)+' · 交卷后不可更改</small></form>';
}
function progressMetrics(p){
 return '<div class="metrics">'+[['复核观测',p.total],['已定案',p.resolved],['待裁决',p.disputed],['收集中',p.collecting],['待领取',p.waiting],['在办领取',p.open_claims+(p.overdue_claims?'（超期 '+p.overdue_claims+'）':'')]].map(([k,v])=>'<div><span>'+k+'</span><strong>'+esc(v)+'</strong></div>').join('')+'</div>';
}
function adminView(d){
 const rows=(d.items||[]).map(i=>({idx:'第 '+(i.idx+1)+' 行',record:recOf(i.record),status:ItemStatus[i.status]||i.status,
  opinions:(i.opinions||[]).map(o=>esc(o.reviewer)+'：'+esc(Decision[o.decision]||'')+'（'+esc(o.rationale)+'）').join('<br>')||'—',
  adjudication:i.adjudication?esc(i.adjudication.reviewer)+'：'+esc(Decision[i.adjudication.decision]||'')+'（'+esc(i.adjudication.rationale)+'）':'—',
  final:(Decision[i.final_decision]||'—')}));
 const open=(d.open_assignments||[]).map(a=>'<article><div><strong>'+esc(a.assignee)+'</strong><p>第 '+(a.idx+1)+' 行 · '+(a.kind==='review'?'复核':'裁决')+' · 到期 '+date(a.due_at)+'</p></div><button class="button small" data-reassign="'+a.id+'" '+(a.overdue?'':'disabled')+'>'+(a.overdue?'改派 ↗':'未超期')+'</button></article>');
 const revoked=(d.revoked||[]).map(a=>'<li><strong>'+esc(a.assignee)+'</strong><span>第 '+(a.idx+1)+' 行 · '+(a.kind==='review'?'复核':'裁决')+' · 已改派 '+date(a.revoked_at)+'</span></li>');
 return '<section class="panel"><div class="section-title"><h2>观测明细</h2><span>'+(d.items||[]).length+' 条复核观测 · 意见对复核员隔离</span></div>'
  +'<div class="table-wrap"><table><thead><tr><th>观测</th><th>冻结数据</th><th>状态</th><th>双评意见</th><th>裁决</th><th>定案</th></tr></thead><tbody>'
  +rows.map(r=>'<tr><td>'+r.idx+'</td><td>'+r.record+'</td><td>'+esc(r.status)+'</td><td>'+r.opinions+'</td><td>'+r.adjudication+'</td><td>'+esc(r.final)+'</td></tr>').join('')+'</tbody></table></div></section>'
  +'<div class="two-columns"><section class="panel"><div class="section-title"><h2>在办领取</h2><span>超期可改派，旧领取晚到意见将被拒绝</span></div><div class="schedule-list">'+(open.join('')||'<p class="empty">当前没有在办领取。</p>')+'</div></section>'
  +'<section class="panel"><div class="section-title"><h2>已改派记录</h2></div><ul class="timeline">'+(revoked.join('')||'<li><strong>暂无</strong></li>')+'</ul></section></div>';
}
function reviewerView(d){
 const open=(d.mine||[]).filter(a=>a.status==='open'),done=(d.mine||[]).filter(a=>a.status!=='open');
 return '<section class="panel"><div class="section-title"><h2>我的复核台</h2><span>双方交卷前互不可见对方意见</span></div>'
  +(d.status==='open'?'<button class="primary" id="claim">领取下一条 ↗</button>':'<p class="hint">本批次已结案，停止领件。</p>')
  +(open.length?'<h3 class="subheading">待交卷</h3>'+open.map(a=>opinionForm(a,'交卷')).join(''):'')
  +(done.length?'<h3 class="subheading">我的已交意见</h3><ul class="timeline">'+done.map(a=>'<li><strong>第 '+(a.idx+1)+' 行 · '+esc(Decision[a.opinion]||a.opinion)+'</strong><span>'+esc(a.rationale)+' · '+date(a.submitted_at)+'</span></li>').join('')+'</ul>':'')
  +'</section>';
}
function adjudicatorView(d){
 const open=(d.mine||[]).filter(a=>a.status==='open'),done=(d.mine||[]).filter(a=>a.status!=='open');
 return '<section class="panel"><div class="section-title"><h2>我的裁决台</h2><span>仅可裁决本人未参与复核的分歧</span></div>'
  +(d.status==='open'?'<button class="primary" id="claim-adjudication">领取分歧裁决 ↗</button>':'<p class="hint">本批次已结案。</p>')
  +(open.length?'<h3 class="subheading">待裁决</h3>'+open.map(a=>opinionForm(a,'裁决定案')).join(''):'')
  +(done.length?'<h3 class="subheading">我的裁决记录</h3><ul class="timeline">'+done.map(a=>'<li><strong>第 '+(a.idx+1)+' 行 · '+esc(Decision[a.opinion]||a.opinion)+'</strong><span>'+esc(a.rationale)+' · '+date(a.submitted_at)+'</span></li>').join('')+'</ul>':'')
  +'</section>';
}
function closedView(d){
 const rows=(d.conclusions||[]).map(c=>({idx:'第 '+(c.idx+1)+' 行',record:recOf(c.record),final:Decision[c.final_decision]||c.final_decision,
  rationale:c.rationale,opinions:(c.opinions||[]).map(o=>esc(o.who)+'：'+esc(Decision[o.decision]||'')+'（'+esc(o.rationale)+'）').join('<br>')}));
 return '<section class="panel"><div class="section-title"><h2>研究批次已生成</h2><span>仅含保留观测并附逐条依据</span></div>'
  +'<p>研究批次 <strong>研究批次 · '+esc(d.name)+'</strong> 已可在数据接入与分析工作台中使用；未完成复核的样本不会进入分析。<a href="#/datasets">查看数据批次 ↗</a></p></section>'
  +'<section class="panel"><div class="section-title"><h2>历史结论</h2><span>原观测与全部意见永久保留</span></div>'
  +'<div class="table-wrap"><table><thead><tr><th>观测</th><th>原观测数据</th><th>定案</th><th>逐条依据</th><th>意见记录</th></tr></thead><tbody>'
  +rows.map(r=>'<tr><td>'+r.idx+'</td><td>'+r.record+'</td><td>'+esc(r.final)+'</td><td>'+esc(r.rationale)+'</td><td>'+r.opinions+'</td></tr>').join('')+'</tbody></table></div></section>';
}
export async function reviewPage(id){
 const [list,allDatasets]=await Promise.all([reviews.list(),datasets.list()]);
 workspace.reviews=list;
 const selected=id?await reviews.get(id):(list.length?await reviews.get(list[0].id):null);
 const role=session.user.role,canManage=['admin','analyst'].includes(role);
 let detail='<div class="empty">尚无复核批次。'+(canManage?'从左侧发起一次双盲复核。':'')+'</div>';
 if(selected){
  const d=selected,p=d.progress;
  detail='<div class="result-selector"><strong>'+esc(d.name)+'</strong><span class="status">'+esc(ReviewStatus[d.status]||d.status)+'</span><span>源批次 '+esc(d.dataset_name)+' · 冻结 '+d.frozen_rows+' 条</span><span>SHA256 '+esc(d.frozen_checksum.slice(0,14))+'…</span>'
   +(role==='admin'&&d.status==='open'?'<button class="button small" id="close-review" '+(p.ready?'':'disabled')+'>'+(p.ready?'结案并生成研究批次 ↗':'未齐或未裁决 · 不能结案')+'</button>':'')+'</div>'
  +progressMetrics(p)
  +(role==='reviewer'?reviewerView(d):role==='adjudicator'?adjudicatorView(d):canManage?adminView(d):'<section class="panel"><p class="hint">复核进行中。结案后此处公布研究批次与历史结论。</p></section>')
  +(d.status==='closed'?closedView(d):'');
 }
 return heading('04 / DOUBLE-BLIND REVIEW','观测双盲复核','单人删改异常客流可能扭曲补车信号。发起复核即冻结批次，每条观测由两名复核员背对背判定，分歧由未参与的裁决员定案。')
  +'<div class="review-grid"><section class="panel"><div class="section-title"><h2>复核批次</h2><span>'+list.length+' 批</span></div><div class="batch-list">'
  +list.map(r=>'<a class="batch-item" href="#/reviews/'+r.id+'"><strong>'+esc(r.name)+'</strong><span>'+esc(ReviewStatus[r.status]||r.status)+' · 已定案 '+r.progress.resolved+'/'+r.progress.total+'</span><small>待裁决 '+r.progress.disputed+' · 在办 '+r.progress.open_claims+'</small></a>').join('')
  +'</div>'+(canManage?'<div class="section-title"><h2>发起复核</h2></div><form id="review-form"><label>复核名称<input name="name" required minlength="2" maxlength="160" placeholder="例如：12 月异常客流复核"></label><label>源数据批次<select name="dataset_id">'+allDatasets.map(x=>'<option value="'+x.id+'">'+esc(x.name)+' · '+x.rows+' 条</option>').join('')+'</select></label><label>观测行号（从 1 开始，逗号分隔；留空复核全部）<textarea name="indexes" rows="2" placeholder="例如：15, 37, 102"></textarea></label><label>领取时限<select name="ttl_seconds"><option value="86400">1 天</option><option value="259200">3 天</option><option value="604800">7 天</option><option value="60">60 秒（验收）</option></select></label><button type="submit" class="primary" '+(allDatasets.length?'':'disabled')+'>冻结批次并发起 ↗</button><p class="hint">发起即冻结源批次快照；超期领取可由负责人改派。</p></form>':'<p class="hint">发起复核需分析员或负责人权限。</p>')+'</section>'
  +'<section>'+detail+'</section></div>';
}
export function bindReviews(refresh){
 const createForm=document.querySelector('#review-form');
 if(createForm)submit(createForm,async f=>{
  const raw=(f.get('indexes')||'').trim();
  const indexes=raw?raw.split(/[,，\s]+/).filter(Boolean).map(s=>{const n=Number(s);if(!Number.isInteger(n)||n<1)throw new Error('行号须为从 1 开始的整数');return n-1;}):null;
  const r=await reviews.create({name:f.get('name'),dataset_id:Number(f.get('dataset_id')),indexes,ttl_seconds:Number(f.get('ttl_seconds'))});
  notify('复核批次已冻结并发起');location.hash='#/reviews/'+r.id;
 });
 document.querySelector('#claim')?.addEventListener('click',async()=>{try{const id=location.hash.split('/')[2];await reviews.claim(id);notify('已领取，请在交卷前独立判定');await refresh();}catch(e){notify(e.message,true);}});
 document.querySelector('#claim-adjudication')?.addEventListener('click',async()=>{try{const id=location.hash.split('/')[2];await reviews.claimAdjudication(id);notify('已领取分歧裁决');await refresh();}catch(e){notify(e.message,true);}});
 document.querySelectorAll('.opinion-form').forEach(form=>submit(form,async f=>{await reviews.submit(form.dataset.assignment,{decision:f.get('decision'),rationale:f.get('rationale')});notify('已交卷');await refresh();}));
 document.querySelectorAll('[data-reassign]').forEach(b=>b.onclick=async()=>{try{await reviews.reassign(b.dataset.reassign);notify('已改派，该条重新开放领取');await refresh();}catch(e){notify(e.message,true);}});
 document.querySelector('#close-review')?.addEventListener('click',async()=>{try{const id=location.hash.split('/')[2];await reviews.close(id);notify('已结案，研究批次已生成');await refresh();}catch(e){notify(e.message,true);}});
}
