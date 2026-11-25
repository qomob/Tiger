"""Offline, advisory-only rule engine. No official readiness authority."""
import argparse, json, math, hashlib, sys
from collections import Counter
from datetime import date
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
RULES=json.loads((ROOT/'references/rules.json').read_text())
CAT={x['id']:x for x in json.loads((ROOT/'references/categories.json').read_text())}
def score(cid, scores):
    w=CAT[cid]['weights']
    if w is None: raise ValueError('nomination: no published rubric')
    if len(scores)!=len(w) or any(type(x) not in (int,float) or not math.isfinite(x) or not 0<=x<=10 for x in scores): raise ValueError('invalid scores')
    return round(sum(a*b/10 for a,b in zip(scores,w.values())),2)
def fees(counts):
    if any(k not in RULES['fee_cny'] or type(v)!=int or v<0 for k,v in counts.items()): raise ValueError('invalid fee counts')
    return sum(RULES['fee_cny'][k]*v for k,v in counts.items())
def audit(p, root):
    issues=[]; results={}; valid=set(); facts={}; root=Path(root).resolve()
    def issue(sev,code,msg): issues.append(dict(severity=sev,code=code,message=msg))
    if not isinstance(p,dict): raise ValueError('project must be object')
    allowed={'project_id','edition','start','end','categories','human_checks','company_case_count','facts','drafts','scores','media'}
    if set(p)-allowed: issue('P0','UNREVIEWED_FIELDS','Unknown project fields: '+', '.join(sorted(set(p)-allowed)))
    if type(p.get('edition')) is not int or p.get('edition')!=18: issue('P0','EDITION','Only edition 18 supported')
    if not isinstance(p.get('project_id'),str) or not p['project_id'].strip(): issue('P0','PROJECT_ID','Missing canonical project id')
    ids=p.get('categories',[])
    if not isinstance(ids,list) or not ids or any(not isinstance(x,str) for x in ids): ids=[]; issue('P0','CATEGORY','Invalid/missing categories')
    if len(set(ids))!=len(ids): issue('P0','DUPLICATE','Repeated category')
    groups=Counter()
    for cid in ids:
        if cid not in CAT: issue('P0','CATEGORY_UNKNOWN',cid); continue
        c=CAT[cid]; groups[c['group']]+=1
        if c['mode']=='nomination': issue('P0','NOMINATION',cid+' is nomination-only')
    for g,n in groups.items():
        if g in RULES['limits'] and n>RULES['limits'][g]: issue('P0','LIMIT',g)
    if set(groups)&{'general','special','creative','commerce'}:
        try:
            a,b=(date.fromisoformat(p[k]) for k in ('start','end'))
            lo,hi=(date.fromisoformat(RULES['dates'][k]) for k in ('work_start','work_end'))
            if a>b or a<lo or b>hi: issue('P0','DATE','Outside case window or reversed; cross-period exceptions require organizer confirmation')
        except (KeyError,TypeError,ValueError): issue('REVIEW','DATE_UNKNOWN','Missing/invalid work dates')
    if any(g.startswith('brand_') for g in groups) or 'technology' in groups: issue('REVIEW','ANNUAL_SCOPE','Confirm annual/product period and specific eligibility with organizer')
    checks=p.get('human_checks',{})
    if not isinstance(checks,dict): issue('P0','CHECK_SCHEMA','Invalid human review map'); checks={}
    check_keys={'commercial_entity','rights','public_permission','stamped_confirmation','legal_ethics','prior_award_compliance','category_fit','project_identity','all_media_reviewed','claim_coverage','source_original_review','evidence_sufficiency','differentiation','budget_acceptance','anonymity','brand_owner'}
    if set(checks)-check_keys or any(type(v) is not bool for v in checks.values()): issue('P0','CHECK_SCHEMA','Unknown or non-boolean human review field')
    for k in ('commercial_entity','rights','public_permission','stamped_confirmation','legal_ethics','prior_award_compliance','category_fit','project_identity','all_media_reviewed','claim_coverage','source_original_review','evidence_sufficiency','differentiation','budget_acceptance'):
        if checks.get(k) is False: issue('P0' if k not in ('differentiation','evidence_sufficiency') else 'REVIEW',k,'Human review reports failed')
        elif checks.get(k) is not True: issue('REVIEW',k,'Human confirmation absent')
    if set(groups)&{'general','special','creative','commerce','technology'} and checks.get('anonymity') is not True: issue('P0' if checks.get('anonymity') is False else 'REVIEW','ANONYMITY','Human anonymity check not passed')
    if any(g.startswith('brand_') for g in groups) and checks.get('brand_owner') is not True: issue('REVIEW','BRAND_OWNER','Confirm brand owner eligibility')
    count=p.get('company_case_count')
    if type(count)!=int or count<1 or count>20: issue('P0' if type(count)==int and count<1 else 'REVIEW','COMPANY_COUNT','At least the current project; confirm total annual entries; principle <=20')
    entries=p.get('facts',[])
    if not isinstance(entries,list) or not entries: issue('REVIEW','NO_FACTS','No fact ledger'); entries=[]
    for f in entries:
        if not isinstance(f,dict): issue('P0','FACT_SCHEMA','Invalid fact'); continue
        if set(f)-{'id','claim','quote','source','sha256','conflict','public','attribution','original_reviewed'}: issue('P0','FACT_SCHEMA','Unreviewed fact field'); continue
        fid=f.get('id'); claim=f.get('claim'); quote=f.get('quote'); path=f.get('source'); sha=f.get('sha256')
        if not isinstance(fid,str) or not fid.strip() or fid in facts: issue('P0','FACT_ID','Missing or duplicate fact ID'); continue
        facts[fid]=f
        if not all(isinstance(v,str) and v.strip() for v in (claim,quote,path,sha)): issue('P0','FACT_FIELDS',fid); continue
        if f.get('conflict') is not False or f.get('public') is not True: issue('P0','FACT_PERMISSION_CONFLICT',fid); continue
        if f.get('attribution') not in ('descriptive','causal_reviewed','not_applicable') or f.get('original_reviewed') is not True: issue('REVIEW','FACT_REVIEW',fid); continue
        try:
            rel=Path(path)
            if rel.is_absolute(): raise ValueError('absolute path')
            src=(root/rel).resolve(); src.relative_to(root)
            if not src.is_file() or src.stat().st_size>10_000_000: raise ValueError('missing/oversize text source')
            data=src.read_bytes(); txt=data.decode('utf-8')
            if hashlib.sha256(data).hexdigest()!=sha or quote not in txt.splitlines() or claim != quote: raise ValueError('hash/quote/claim mismatch')
            valid.add(fid)
        except (OSError,ValueError,UnicodeError): issue('P0','BINDING',fid+' source/hash/exact text failed')
    drafts=p.get('drafts',{})
    if not isinstance(drafts,dict): issue('P0','DRAFT_SCHEMA','Invalid draft map'); drafts={}
    for cid in ids:
        blocks=drafts.get(cid)
        if not isinstance(blocks,list) or not blocks: issue('REVIEW','DRAFT_MISSING',cid); continue
        for block in blocks:
            if not isinstance(block,dict) or set(block)!={'fact_id','text'} or not isinstance(block.get('fact_id'),str): issue('P0','DRAFT_BINDING',cid); continue
            fid=block['fact_id']
            if fid not in valid or block.get('text')!=facts[fid]['claim']: issue('P0','DRAFT_BINDING',cid+' '+fid)
    for cid in drafts:
        if cid not in ids: issue('P0','DRAFT_CATEGORY',cid)
    media=p.get('media',[])
    if not isinstance(media,list): media=[]; issue('P0','MEDIA_SCHEMA','Invalid media list')
    images=av=0
    for m in media:
        if not isinstance(m,dict): issue('P0','MEDIA_SCHEMA','Invalid item'); continue
        kind=m.get('kind'); fmt=m.get('format'); size=m.get('bytes')
        if set(m)-{'kind','format','bytes','embed_reviewed'}: issue('P0','MEDIA_SCHEMA','Unreviewed media field')
        if kind=='image':
            images+=1
            if fmt!='jpg': issue('P0','MEDIA_FORMAT','JPG required')
            if size is not None and (type(size)!=int or size<=0): issue('P0','MEDIA_SIZE','Image declared bytes must be positive integer')
        elif kind in ('video','audio','online_video'):
            av+=1
            if kind=='online_video':
                if m.get('embed_reviewed') is not True: issue('REVIEW','EMBED','Verify designated platform')
            elif fmt!=('mp4' if kind=='video' else 'mp3') or type(size)!=int or not 0<size<=RULES['media']['size_limit_decimal_bytes_conservative']: issue('P0','MEDIA_SPEC','MP4/MP3 and <=100M required (conservative)')
        else: issue('P0','MEDIA_KIND','Unknown media kind')
    if set(ids)&{'special-07','special-08','creative-02','creative-03'} and not any(isinstance(m,dict) and m.get('kind') in ('video','online_video') for m in media): issue('REVIEW','VIDEO_MISSING','Video-dependent category: supply material or verify official exception')
    if 'special-09' in ids and not any(isinstance(m,dict) and m.get('kind')=='audio' for m in media): issue('REVIEW','AUDIO_MISSING','Audio-dependent category: supply material or verify official exception')
    if images>12: issue('REVIEW','IMAGE_COUNT','Principle <=12 images')
    if av>5: issue('P0','AV_COUNT','AV limit 5')
    sc=p.get('scores',{})
    if not isinstance(sc,dict): sc={}; issue('REVIEW','SCORE_SCHEMA','Invalid scores')
    if set(sc)-set(ids): issue('P0','SCORE_CATEGORY','Scores for unselected category')
    for cid in ids:
        if cid not in CAT or CAT[cid]['weights'] is None: continue
        try:
            if cid not in sc: raise ValueError('missing scores')
            v=score(cid,sc[cid]); results[cid]={'score':v,'score_status':'UNVERIFIED_INPUT_ARITHMETIC_ONLY','evidence_supported_score':None,'evidence_score_range':[0,100],'value':'INSUFFICIENT_EVIDENCE' if not valid or checks.get('evidence_sufficiency') is not True else 'NOT_RECOMMENDED' if v<70 or checks.get('differentiation') is False else 'CONDITIONAL'}
        except (TypeError,ValueError,OverflowError): issue('REVIEW','SCORE',cid)
    status='BLOCKED' if any(x['severity']=='P0' for x in issues) else 'REVIEW' if issues else 'INTERNAL_CHECKS_PASSED'
    if status!='INTERNAL_CHECKS_PASSED':
        for result in results.values():
            result['decision_gate']='BLOCKED' if status=='BLOCKED' else 'REVIEW_REQUIRED'
    return {'status':status,'official_submission':'UNVERIFIED_MANUAL_CONFIRMATION_REQUIRED','verified_text_bindings':sorted(valid),'scores':results,'issues':issues,'limitations':'Text bindings only; human assertions, score inputs, declared media metadata and any final rendered manuscript not independently verified; no official readiness or award probability.'}
def strict_json(text):
    def pairs(items):
        obj={}
        for k,v in items:
            if k in obj: raise ValueError('duplicate JSON key: '+k)
            obj[k]=v
        return obj
    def constant(v): raise ValueError('nonfinite JSON constant: '+v)
    return json.loads(text,object_pairs_hook=pairs,parse_constant=constant)

def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest='cmd',required=True)
    c=sub.add_parser('catalog'); c.add_argument('--group'); s=sub.add_parser('score'); s.add_argument('category'); s.add_argument('values',nargs='+',type=float)
    f=sub.add_parser('fees');
    for k in RULES['fee_cny']: f.add_argument('--'+k.replace('_','-'),type=int,default=0)
    a=sub.add_parser('audit'); a.add_argument('project'); a.add_argument('--evidence-root',required=True)
    args=ap.parse_args(); rc=0
    try:
        if args.cmd=='catalog': out=[x for x in CAT.values() if not args.group or x['group']==args.group]
        elif args.cmd=='score': out={'internal_score':score(args.category,args.values),'score_status':'UNVERIFIED_INPUT_ARITHMETIC_ONLY'}
        elif args.cmd=='fees': out={'scenario_cny':fees({k:getattr(args,k) for k in RULES['fee_cny']}),'not_prediction':True}
        else:
            out=audit(strict_json(Path(args.project).read_text(encoding='utf-8')),args.evidence_root); rc={'BLOCKED':3,'REVIEW':2,'INTERNAL_CHECKS_PASSED':0}[out['status']]
    except (ValueError,KeyError,TypeError,OSError,OverflowError) as e: out={'status':'BLOCKED','error':str(e)}; rc=3
    print(json.dumps(out,ensure_ascii=False,indent=2)); return rc
if __name__=='__main__':
    sys.exit('Legacy baseline only; use scripts/roar.py for V2 audit.')
