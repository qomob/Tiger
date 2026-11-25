"""V2 evidence-bound advisory audit. No authority to submit. Python 3.10+.
Operator supplies a separately trusted Ed25519 public key; never trust a key in project data.
"""
import argparse, hashlib, json, math, re, shutil, subprocess, sys, tempfile, unicodedata
from datetime import date
from pathlib import Path
from decimal import Decimal, InvalidOperation
from legacy import CAT, RULES, score, fees, strict_json, audit as legacy_audit
ROOT=Path(__file__).resolve().parents[1]
PROFILES=json.loads((ROOT/'references/category-profiles.json').read_text())
HEX=re.compile(r'^[0-9a-f]{64}$')

def digest(data): return hashlib.sha256(data).hexdigest()
def canonical(obj): return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
def ident(x): return isinstance(x,str) and bool(x.strip()) and x==x.strip()
def norm(x): return ' '.join(unicodedata.normalize('NFKC',x).casefold().split())
def finite(x): return type(x) in (int,float) and math.isfinite(x)
def safe_file(root,path,limit=100_000_000):
    if not ident(path) or Path(path).is_absolute(): raise ValueError('invalid relative path')
    candidate=root/path
    if any(x.is_symlink() for x in [candidate,*candidate.parents] if x!=root and root in x.parents): raise ValueError('symlink prohibited')
    p=candidate.resolve(); p.relative_to(root)
    if not p.is_file() or p.stat().st_size<=0 or p.stat().st_size>limit: raise ValueError('missing/empty/oversize file')
    data=p.read_bytes()
    if len(data)>limit: raise ValueError('oversize file')
    return p,data

def trusted_signature(p,key,sig):
    if not key or not sig: return False,'No independently supplied signature/key'
    if not shutil.which('openssl'): return False,'OpenSSL unavailable'
    try:
        keypath=str(Path(key).resolve())
        keyinfo=subprocess.run(['openssl','pkey','-pubin','-in',keypath,'-text','-noout'],capture_output=True,timeout=8)
        if keyinfo.returncode!=0 or b'ED25519' not in keyinfo.stdout: return False,'Expected Ed25519 public key'
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'snapshot.json'; f.write_bytes(canonical(p))
            proc=subprocess.run(['openssl','pkeyutl','-verify','-pubin','-inkey',str(Path(key).resolve()),'-rawin','-in',str(f),'-sigfile',str(Path(sig).resolve())],capture_output=True,timeout=8)
            return proc.returncode==0,'Signature verifies against operator-supplied key' if proc.returncode==0 else 'Invalid signature or key'
    except (OSError,ValueError,subprocess.SubprocessError) as e: return False,str(e)

def file_record(root,rec,keys):
    if not isinstance(rec,dict) or set(rec)!=keys: raise ValueError('record fields invalid')
    if not isinstance(rec.get('sha256'),str) or not HEX.fullmatch(rec['sha256']): raise ValueError('invalid hash')
    path,data=safe_file(root,rec['path'])
    if digest(data)!=rec['sha256']: raise ValueError('file hash mismatch')
    return path,data

def audit(p,root,public_key=None,signature=None):
    root=Path(root).resolve(); issues=[]; bindings={}; meta={}; eligible=set(); score_results={}; reviewed_sources=set()
    def add(sev,code,msg,category=None):
        issues.append(dict(severity=sev,code=code,message=str(msg),**({'category':category} if category else {})))
    def result(status='BLOCKED'):
        return {'schema_version':2,'status':status,'official_submission':'UNVERIFIED_MANUAL_CONFIRMATION_REQUIRED','scores':score_results,'text_bound_facts':sorted(bindings),'review_attested_facts':sorted(eligible),'issues':issues,'limitations':'Signed attestations are not independent proof of source truth or causality. Trusted key custody and reviewer independence are external. Exact text final file only; official fields and visual/audio semantic review are not automated.'}
    if not isinstance(p,dict) or p.get('schema_version')!=2 or type(p.get('schema_version')) is not int:
        add('REVIEW','MIGRATION_REQUIRED','Use V2 envelope. Legacy project input is not an approval.'); return result('REVIEW')
    expected={'schema_version','base','author_id','reviewer_id','source_records','fact_meta','assessments','final_files','media_files','portfolio'}
    if set(p)!=expected or not isinstance(p.get('base'),dict): add('P0','ENVELOPE','Unknown/missing V2 fields'); return result()
    b=p['base']; project=b.get('project_id'); ids=b.get('categories',[])
    try: old=legacy_audit(b,root)
    except (ValueError,KeyError,TypeError,OSError,OverflowError,AttributeError) as e: add('P0','BASE_SCHEMA',e); return result()
    if not ident(project): add('P0','PROJECT_ID_FORMAT','Canonical project ID required')
    issues.extend(x for x in old['issues'] if not (x['code']=='SCORE' and not b.get('scores'))); signed,why=trusted_signature(p,public_key,signature)
    independent=ident(p['author_id']) and ident(p['reviewer_id']) and norm(p['author_id'])!=norm(p['reviewer_id'])
    trusted=signed and independent
    if not trusted: add('REVIEW','INDEPENDENT_REVIEW_REQUIRED',why if not signed else 'Author and reviewer must differ')
    if not isinstance(ids,list) or any(not isinstance(x,str) for x in ids): return result()
    # Source registry describes provenance, not proof of actual truth. Hash the original as well as extract.
    sr=p['source_records']; fm=p['fact_meta']; sources={}
    if not isinstance(sr,dict) or not isinstance(fm,dict): add('P0','EVIDENCE_SCHEMA','Source/fact maps required'); return result()
    for path,r in sr.items():
        try:
            if not isinstance(r,dict) or set(r)!={'project_id','owner','type','original_path','original_sha256','review_status'}: raise ValueError('source record fields')
            if r['project_id']!=project or not ident(r['owner']): raise ValueError('source belongs to another/unknown project')
            if r['type'] not in ('client_system','client_document','platform_export','third_party','self_report','synthetic'): raise ValueError('unknown source type')
            _,raw=safe_file(root,r['original_path']); _,extract=safe_file(root,path,10_000_000)
            if digest(raw)!=r['original_sha256']: raise ValueError('original hash mismatch')
            sources[path]=r
            if trusted and r['review_status']=='attested_original' and r['type'] not in ('self_report','synthetic'): reviewed_sources.add(path)
            else: add('REVIEW','SOURCE_UNATTESTED',path)
        except (ValueError,OSError,TypeError,KeyError) as e: add('P0','SOURCE_PROVENANCE',f'{path}: {e}')
    facts=b.get('facts',[]); fact_ids=set(); metric_values={}
    if not isinstance(facts,list): add('P0','FACT_SCHEMA','Invalid facts'); return result()
    for f in facts:
        if not isinstance(f,dict) or not ident(f.get('id')): continue
        fid=f['id']; fact_ids.add(fid)
        if fid not in old['verified_text_bindings']: continue
        m=fm.get(fid)
        try:
            if not isinstance(m,dict) or set(m)!={'project_id','line','kind','metric','locator','causal_status'}: raise ValueError('missing/unknown fact metadata')
            if m['project_id']!=project or f['source'] not in sources: raise ValueError('wrong project or unregistered source')
            if not ident(m['locator']) or type(m['line']) is not int or m['line']<1: raise ValueError('invalid locator')
            _,raw=safe_file(root,f['source'],10_000_000); lines=raw.decode('utf-8').splitlines()
            if m['line']>len(lines) or lines[m['line']-1]!=f['quote']: raise ValueError('line/quote mismatch')
            if m['kind'] not in ('context','mechanism','metric','artifact','authorization','counterevidence'): raise ValueError('unknown claim kind')
            if m['causal_status'] not in ('descriptive','not_applicable','unproven','attested_design'): raise ValueError('invalid causal status')
            if f['attribution']=='causal_reviewed' and m['causal_status']!='attested_design': add('REVIEW','CAUSAL_UNPROVEN',fid); continue
            if m['kind']=='metric':
                metric=m['metric']; mk={'name','unit','scope','start','end','comparison','value','definition'}
                if not isinstance(metric,dict) or set(metric)!=mk or not all(ident(metric[k]) for k in mk-{'value'}): raise ValueError('metric fields required')
                if not finite(metric['value']): raise ValueError('metric value invalid')
                v=Decimal(str(metric['value'])); lo=date.fromisoformat(metric['start']); hi=date.fromisoformat(metric['end'])
                if lo>hi: raise ValueError('metric period reversed')
                # lexical numeric check, not semantic extraction; signed reviewer must confirm unit/meaning.
                nums=[Decimal(x) for x in re.findall(r'(?<![\d.])-?\d+(?:\.\d+)?',unicodedata.normalize('NFKC',f['quote']).replace(',',''))]
                if v not in nums: raise ValueError('metric number not present in source line')
                key=tuple(norm(metric[k]) for k in ('name','unit','scope','start','end','comparison'))
                metric_values.setdefault(key,[]).append((fid,v))
            elif m['metric'] is not None: raise ValueError('metric metadata on nonmetric fact')
            bindings[fid]=f; meta[fid]=m
            if f['source'] in reviewed_sources: eligible.add(fid)
        except (ValueError,TypeError,OSError,UnicodeError,InvalidOperation,KeyError) as e: add('P0','FACT_PROVENANCE',f'{fid}: {e}')
    if set(fm)-fact_ids: add('P0','ORPHAN_FACT_META','Unmatched metadata')
    for k,vals in metric_values.items():
        if len({v for _,v in vals})>1:
            add('P0','METRIC_CONFLICT',', '.join(fid for fid,_ in vals)); eligible.difference_update(fid for fid,_ in vals)
    # Portfolio: current work expands to one entry per selected category, count cannot understate it.
    portfolio=p['portfolio']; pairs=[]
    try:
        if not isinstance(portfolio,list) or not portfolio: raise ValueError('portfolio required')
        for row in portfolio:
            if not isinstance(row,dict) or set(row)!={'project_id','category_id'} or not ident(row['project_id']) or row['category_id'] not in CAT or CAT[row['category_id']]['mode']!='direct': raise ValueError('invalid portfolio entry')
            pairs.append((norm(row['project_id']),row['category_id']))
        if len(set(pairs))!=len(pairs) or not {(norm(project),c) for c in ids}.issubset(pairs): raise ValueError('duplicate or missing selected work/category')
        if b.get('company_case_count')!=len(pairs): raise ValueError('declared count does not equal portfolio rows')
        # conservative group counts apply per normalized project ID; actual entity/work aliases require external review
        from collections import Counter
        for (pid,grp),count in Counter((pid,CAT[c]['group']) for pid,c in pairs).items():
            if count>RULES['limits'].get(grp,999): raise ValueError('portfolio group limit exceeded')
    except (ValueError,TypeError,KeyError) as e: add('P0','PORTFOLIO',e)
    # Reverse check exact canonical UTF-8 final draft, including unregistered text lines.
    ff=p['final_files']
    if not isinstance(ff,dict): add('P0','FINAL_SCHEMA','Final file map required'); ff={}
    if set(ff)-set(ids): add('P0','FINAL_CATEGORY','Unselected final file')
    for cid in ids:
        if cid not in ff: add('REVIEW','FINAL_MISSING',cid,cid); continue
        try:
            _,data=file_record(root,ff[cid],{'path','sha256'})
            blocks=b['drafts'][cid]; expected_text=''.join(x['text']+'\n' for x in blocks).encode('utf-8')
            if data!=expected_text or any(x['fact_id'] not in bindings for x in blocks): raise ValueError('final bytes differ from bound draft')
        except (ValueError,KeyError,TypeError,OSError) as e: add('P0','FINAL_MISMATCH',e,cid)
    # Verify actual media bytes and codec/container with ffprobe when available, no semantic claims.
    mf=p['media_files']; declared=b.get('media',[])
    if not isinstance(mf,list) or not isinstance(declared,list) or len(mf)!=len(declared): add('P0','MEDIA_MANIFEST','Media file manifest must align with declarations'); mf=[]
    for i,(rec,m) in enumerate(zip(mf,declared)):
        try:
            if not isinstance(m,dict): raise ValueError('invalid media declaration')
            if m.get('kind')=='online_video': add('REVIEW','ONLINE_MEDIA','External video unverified'); continue
            path,data=file_record(root,rec,{'path','sha256'})
            if m.get('bytes')!=len(data): raise ValueError('declared size mismatch')
            if not shutil.which('ffprobe'): add('REVIEW','MEDIA_PROBE_NOT_RUN',str(i)); continue
            pr=subprocess.run(['ffprobe','-v','error','-protocol_whitelist','file','-format_whitelist','image2,jpeg_pipe,mjpeg,mov,mp4,m4a,3gp,3g2,mj2,mp3','-show_entries','stream=codec_type,codec_name:format=format_name,duration','-of','json',str(path)],capture_output=True,timeout=12)
            if pr.returncode: raise ValueError('invalid media container')
            info=json.loads(pr.stdout); streams=info.get('streams',[]); fmt=info.get('format',{}).get('format_name','').split(','); kind=m.get('kind')
            if kind=='image' and not (data[:2]==b'\xff\xd8' and any(s.get('codec_name')=='mjpeg' for s in streams)): raise ValueError('not JPEG')
            if kind=='video' and not ('mp4' in fmt and any(s.get('codec_type')=='video' for s in streams)): raise ValueError('not MP4 video')
            if kind=='audio' and not ('mp3' in fmt and any(s.get('codec_name')=='mp3' for s in streams)): raise ValueError('not MP3 audio')
            if kind in ('video','audio') and not float(info.get('format',{}).get('duration',0))>0: raise ValueError('no positive duration')
        except (ValueError,KeyError,TypeError,OSError,subprocess.SubprocessError) as e: add('P0','MEDIA_BYTES',e)
    if 'special-06' in ids and not any(isinstance(m,dict) and m.get('kind') in ('video','online_video') for m in declared): add('REVIEW','VIDEO_MISSING','Short drama material missing','special-06')
    # Signed, dimension-specific judgments, distinct from legacy arithmetic; no automated semantic verification.
    ass=p['assessments']
    if not isinstance(ass,dict): add('P0','ASSESSMENT_SCHEMA','Assessment map required'); ass={}
    if set(ass)-set(ids): add('P0','ASSESSMENT_CATEGORY','Unselected assessment')
    def refs(v,nonempty=False): return isinstance(v,list) and all(isinstance(x,str) for x in v) and len(set(v))==len(v) and set(v)<=eligible and (bool(v) or not nonempty)
    for cid in ids:
        if cid not in CAT or CAT[cid]['weights'] is None: continue
        weights=CAT[cid]['weights']; a=ass.get(cid); lower=upper=coverage=0; known={}; fit='UNKNOWN'
        if not isinstance(a,dict) or set(a)!={'fit','dimensions'} or not isinstance(a.get('dimensions'),dict):
            add('REVIEW','ASSESSMENT_MISSING',cid,cid); a={'fit':{},'dimensions':{}}
        fitrec=a['fit']; profile=PROFILES[cid]; needs={x['id'] for x in profile['conditions']}
        if isinstance(fitrec,dict) and set(fitrec)==needs:
            statuses=[]
            for k,r in fitrec.items():
                if isinstance(r,dict) and set(r)=={'status','evidence_ids','reason'} and r['status'] in ('MATCH','MISMATCH','UNKNOWN') and ident(r['reason']) and trusted and refs(r['evidence_ids'],True) and r['status']!='UNKNOWN':
                    # Mechanism criteria cannot be supported by metric-only evidence.
                    allowed_kinds=('mechanism','artifact','counterevidence') if k=='mechanism' else ('context','mechanism','artifact','counterevidence')
                    if not any(meta[x]['kind'] in allowed_kinds for x in r['evidence_ids']): statuses.append('UNKNOWN')
                    else: statuses.append(r['status'])
                else: statuses.append('UNKNOWN')
            fit='MISMATCH' if 'MISMATCH' in statuses else 'MATCH' if all(x=='MATCH' for x in statuses) else 'UNKNOWN'
        if fit=='UNKNOWN': add('REVIEW','CATEGORY_FIT_UNVERIFIED',cid,cid)
        if fit=='MISMATCH': add('REVIEW','CATEGORY_MISMATCH',cid,cid)
        if set(a['dimensions'])-set(weights): add('P0','DIMENSION_UNKNOWN',cid,cid)
        for name,w in weights.items():
            r=a['dimensions'].get(name); ok=False
            if isinstance(r,dict) and set(r)=={'score','support','counter','reason','anchor'}:
                v=r['score']; ok=trusted and finite(v) and 0<=v<=10 and refs(r['support'],True) and refs(r['counter']) and not set(r['support'])&set(r['counter']) and ident(r['reason']) and r['anchor']==anchor(v)
                if ok and v<7 and not refs(r['counter'],True): ok=False
                # Outcomes require an attested metric or an explicit observable artifact for creative/non-sales work.
                if ok and any(s in name for s in ('效果','数据','案例分享','成效','成绩')) and not any(meta[x]['kind'] in ('metric','artifact') for x in r['support']): ok=False
            if ok: lower+=v*w/10; upper+=v*w/10; coverage+=w; known[name]=v
            else: upper+=w
        complete=len(known)==len(weights)
        if not complete: add('REVIEW','DIMENSIONS_UNKNOWN',cid,cid)
        score_results[cid]={'fit':fit,'reviewed_dimensions':known,'score_range':[round(lower,2),round(upper,2)],'weight_coverage':coverage,'score_status':'ATTESTED_HUMAN_JUDGMENT' if complete else 'PARTIAL_OR_UNKNOWN','value':'INSUFFICIENT_EVIDENCE'}
        if cid in old['scores']: score_results[cid]['legacy_input_arithmetic']=old['scores'][cid]['score']
    # Global integrity issues block every recommendation; local fit/score gaps do not turn absence into failure.
    status='BLOCKED' if any(x['severity']=='P0' for x in issues) else 'REVIEW' if issues else 'INTERNAL_REVIEW_ATTESTED'
    for cid,r in score_results.items():
        if status=='BLOCKED': r['value']='BLOCKED'; continue
        if r['fit']=='MISMATCH' and trusted: r['value']='NOT_RECOMMENDED_CATEGORY'; continue
        if r['fit']!='MATCH' or r['score_status']!='ATTESTED_HUMAN_JUDGMENT': continue
        # Value decision can precede production of the final manuscript. Delivery remains independently gated.
        delivery_only={'FINAL_MISSING','DRAFT_MISSING','VIDEO_MISSING','AUDIO_MISSING','MEDIA_PROBE_NOT_RUN','ONLINE_MEDIA','EMBED','IMAGE_COUNT','stamped_confirmation','all_media_reviewed'}
        value_clear=not any(i['code'] not in delivery_only and (i.get('category') in (None,cid)) for i in issues)
        if r['score_range'][1]<70 and value_clear: r['value']='NOT_RECOMMENDED' # attested low dimensions require counterevidence
        elif r['score_range'][0]>=85 and value_clear: r['value']='PRIORITY_INTERNAL'
        else: r['value']='CONDITIONAL'
    for r in score_results.values(): r['delivery_gate']=status
    return result(status)

def anchor(v): return '0-2' if v<=2 else '2-4' if v<=4 else '4-6' if v<=6 else '6-8' if v<=8 else '8-10'

def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest='cmd',required=True)
    c=sub.add_parser('catalog'); c.add_argument('--group'); c.add_argument('--profiles',action='store_true')
    s=sub.add_parser('score'); s.add_argument('category'); s.add_argument('values',nargs='+',type=float)
    f=sub.add_parser('fees'); [f.add_argument('--'+k.replace('_','-'),type=int,default=0) for k in RULES['fee_cny']]
    a=sub.add_parser('audit'); a.add_argument('project'); a.add_argument('--evidence-root',required=True); a.add_argument('--public-key'); a.add_argument('--signature')
    c=sub.add_parser('snapshot'); c.add_argument('project'); c.add_argument('output')
    args=ap.parse_args(); rc=0
    try:
        if args.cmd=='catalog': out=[dict(x,**({'profile':PROFILES.get(x['id'])} if args.profiles else {})) for x in CAT.values() if not args.group or x['group']==args.group]
        elif args.cmd=='score': out={'internal_score':score(args.category,args.values),'score_status':'UNVERIFIED_INPUT_ARITHMETIC_ONLY'}
        elif args.cmd=='fees': out={'scenario_cny':fees({k:getattr(args,k) for k in RULES['fee_cny']}),'not_prediction':True}
        elif args.cmd=='snapshot':
            data=canonical(strict_json(Path(args.project).read_text(encoding='utf-8'))); Path(args.output).write_bytes(data); out={'sha256':digest(data),'note':'Bytes for external review/signing; no approval implied'}
        else:
            out=audit(strict_json(Path(args.project).read_text(encoding='utf-8')),args.evidence_root,args.public_key,args.signature); rc={'BLOCKED':3,'REVIEW':2,'INTERNAL_REVIEW_ATTESTED':0}[out['status']]
    except (ValueError,KeyError,TypeError,OSError,OverflowError,AttributeError) as e: out={'status':'BLOCKED','error':str(e)}; rc=3
    print(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False)); return rc
if __name__=='__main__': sys.exit(main())
