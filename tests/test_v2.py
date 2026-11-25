import copy,json,sys,tempfile,subprocess,shutil,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'scripts'))
from roar import audit, canonical, digest, anchor, PROFILES, CAT, strict_json
class V2(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root=Path(self.tmp.name)
  b=json.loads((ROOT/'assets/sample-project.json').read_text()); data=(ROOT/'assets/sample-evidence.txt').read_bytes(); (self.root/'sample-evidence.txt').write_bytes(data)
  b['human_checks']['differentiation']=True
  b['facts'].append(dict(b['facts'][0],id='FACT-004',claim='对照组未显示稳定的复购提升。',quote='对照组未显示稳定的复购提升。'))
  data+= '对照组未显示稳定的复购提升。\n'.encode(); (self.root/'sample-evidence.txt').write_bytes(data)
  for f in b['facts']: f['sha256']=digest(data)
  cid='special-18'; metric={'name':'复购率','unit':'%','scope':'会员活动组','start':'2026-04-01','end':'2026-05-01','comparison':'本期','value':25,'definition':'复购会员占活动组会员比率'}
  meta={f['id']:{'project_id':b['project_id'],'line':i+2,'kind':kind,'metric':metric if kind=='metric' else None,'locator':f'line {i+2}','causal_status':'descriptive'} for i,(f,kind) in enumerate(zip(b['facts'],['context','metric','mechanism','counterevidence']))}
  final=''.join(x['text']+'\n' for x in b['drafts'][cid]).encode(); (self.root/'final.txt').write_bytes(final)
  dims={k:{'score':9,'support':['FACT-002'] if '效果' in k else ['FACT-003'],'counter':[],'reason':'Synthetic fixture; not genuine expert judgment','anchor':anchor(9)} for k in CAT[cid]['weights']}
  self.p={'schema_version':2,'base':b,'author_id':'fixture-writer','reviewer_id':'fixture-reviewer','source_records':{'sample-evidence.txt':{'project_id':b['project_id'],'owner':'Synthetic client for tests only','type':'client_document','original_path':'sample-evidence.txt','original_sha256':digest(data),'review_status':'attested_original'}},'fact_meta':meta,'assessments':{cid:{'fit':{k:{'status':'MATCH','evidence_ids':['FACT-003'],'reason':'Fixture condition assessment'} for k in ['subject','mechanism']},'dimensions':dims}},'final_files':{cid:{'path':'final.txt','sha256':digest(final)}},'media_files':[],'portfolio':[{'project_id':b['project_id'],'category_id':cid}]}
  self.cid=cid
  if shutil.which('openssl'):
   self.key=self.root/'private.pem'; self.pub=self.root/'pub.pem'; self.sig=self.root/'sig'; self.snap=self.root/'snap'
   subprocess.run(['openssl','genpkey','-algorithm','ED25519','-out',str(self.key)],check=True,capture_output=True)
   subprocess.run(['openssl','pkey','-in',str(self.key),'-pubout','-out',str(self.pub)],check=True,capture_output=True)
 def sign(self):
  if not shutil.which('openssl'): self.skipTest('OpenSSL not installed')
  self.snap.write_bytes(canonical(self.p)); subprocess.run(['openssl','pkeyutl','-sign','-inkey',str(self.key),'-rawin','-in',str(self.snap),'-out',str(self.sig)],check=True,capture_output=True)
 def run_audit(self,signed=False,resign=True):
  if signed:
   if resign:self.sign()
   return audit(self.p,self.root,self.pub,self.sig)
  return audit(self.p,self.root)
 def codes(self,signed=False):return {i['code'] for i in self.run_audit(signed)['issues']}
 def score(self,signed=False):return self.run_audit(signed)['scores'][self.cid]
 def test_profile_coverage(self):
  self.assertEqual(set(PROFILES),{k for k,v in CAT.items() if v['mode']=='direct'});self.assertEqual(len(PROFILES),83)
  for k,v in PROFILES.items():self.assertEqual({x['name']:x['weight'] for x in v['dimensions']},CAT[k]['weights'])
 def test_unsigned_high(self):self.assertEqual(self.score()['value'],'INSUFFICIENT_EVIDENCE');self.assertEqual(self.score()['score_range'],[0,100])
 def test_unsigned_low(self):
  self.p['base']['scores'][self.cid]=[0]*4; self.assertEqual(self.score()['value'],'INSUFFICIENT_EVIDENCE')
 def test_signed_high_fixture(self):self.assertEqual(self.score(True)['value'],'PRIORITY_INTERNAL')
 def test_signed_low_counter(self):
  for d in self.p['assessments'][self.cid]['dimensions'].values():d.update(score=4,anchor=anchor(4),counter=['FACT-004'])
  self.assertEqual(self.score(True)['value'],'NOT_RECOMMENDED')
 def test_signed_low_without_counter(self):
  for d in self.p['assessments'][self.cid]['dimensions'].values():d.update(score=0,anchor=anchor(0))
  self.assertEqual(self.score(True)['value'],'INSUFFICIENT_EVIDENCE')
 def test_partial_range(self):
  d=self.p['assessments'][self.cid]['dimensions']; k=list(d)[0]; del d[k]; w=CAT[self.cid]['weights'][k]; s=self.score(True);self.assertEqual(s['weight_coverage'],100-w);self.assertAlmostEqual(s['score_range'][1]-s['score_range'][0],w)
 def test_signature_tamper(self):
  self.sign(); self.p['base']['scores'][self.cid]=[0]*4; r=self.run_audit(True,False);self.assertIn('INDEPENDENT_REVIEW_REQUIRED',{i['code'] for i in r['issues']});self.assertEqual(r['scores'][self.cid]['value'],'INSUFFICIENT_EVIDENCE')
 def test_self_review(self):self.p['reviewer_id']='FIXTURE-WRITER';self.assertEqual(self.score(True)['value'],'INSUFFICIENT_EVIDENCE')
 def test_source_wrong_project(self):self.p['source_records']['sample-evidence.txt']['project_id']='other';self.assertIn('SOURCE_PROVENANCE',self.codes(True))
 def test_fact_wrong_project(self):self.p['fact_meta']['FACT-001']['project_id']='other';self.assertIn('FACT_PROVENANCE',self.codes(True))
 def test_replay_project_id(self):self.p['base']['project_id']='other';self.assertEqual(self.run_audit(True)['status'],'BLOCKED')
 def test_line_mismatch(self):self.p['fact_meta']['FACT-001']['line']=3;self.assertIn('FACT_PROVENANCE',self.codes())
 def test_self_report_not_verified(self):self.p['source_records']['sample-evidence.txt']['type']='self_report';self.assertEqual(self.score(True)['value'],'INSUFFICIENT_EVIDENCE')
 def test_synthetic_not_verified(self):self.p['source_records']['sample-evidence.txt']['type']='synthetic';self.assertEqual(self.score(True)['value'],'INSUFFICIENT_EVIDENCE')
 def test_no_source(self):self.p['source_records']={};self.assertIn('FACT_PROVENANCE',self.codes())
 def test_original_hash(self):self.p['source_records']['sample-evidence.txt']['original_sha256']='0'*64;self.assertIn('SOURCE_PROVENANCE',self.codes())
 def test_numeric_mismatch(self):self.p['fact_meta']['FACT-002']['metric']['value']=10000;self.assertIn('FACT_PROVENANCE',self.codes())
 def test_conflict(self):
  b=self.p['base']; f=copy.deepcopy(b['facts'][1]);f['id']='FACT-005';f['claim']=f['quote']='活动期会员复购率为35%。';b['facts'].append(f);data=(self.root/'sample-evidence.txt').read_bytes()+ (f['claim']+'\n').encode();(self.root/'sample-evidence.txt').write_bytes(data)
  for f in b['facts']:f['sha256']=digest(data)
  self.p['source_records']['sample-evidence.txt']['original_sha256']=digest(data);m=copy.deepcopy(self.p['fact_meta']['FACT-002']);m['line']=6;m['metric']['value']=35;self.p['fact_meta']['FACT-005']=m;self.assertIn('METRIC_CONFLICT',self.codes(True))
 def test_fit_missing(self):self.p['assessments'][self.cid]['fit']={};self.assertEqual(self.score(True)['fit'],'UNKNOWN')
 def test_fit_mismatch(self):self.p['assessments'][self.cid]['fit']['mechanism']['status']='MISMATCH';self.assertEqual(self.score(True)['value'],'NOT_RECOMMENDED_CATEGORY')
 def test_metric_only_fit(self):self.p['assessments'][self.cid]['fit']['mechanism']['evidence_ids']=['FACT-002'];self.assertEqual(self.score(True)['fit'],'UNKNOWN')
 def test_context_only_mechanism(self):
  self.p['assessments'][self.cid]['fit']['mechanism']['evidence_ids']=['FACT-001'];self.assertEqual(self.score(True)['fit'],'UNKNOWN')
 def test_negative_before_final(self):
  self.p['final_files']={}
  for d in self.p['assessments'][self.cid]['dimensions'].values():d.update(score=4,anchor=anchor(4),counter=['FACT-004'])
  s=self.score(True);self.assertEqual(s['value'],'NOT_RECOMMENDED');self.assertEqual(s['delivery_gate'],'REVIEW')
 def test_outcome_without_metric(self):
  for k,d in self.p['assessments'][self.cid]['dimensions'].items():
   if '效果' in k:d['support']=['FACT-003']
  self.assertLess(self.score(True)['weight_coverage'],100)
 def test_final_tamper(self):
  path=self.root/'final.txt';path.write_bytes(path.read_bytes()+b'new text\n');self.assertIn('FINAL_MISMATCH',self.codes(True))
 def test_final_rehash_injection(self):
  path=self.root/'final.txt';data=path.read_bytes()+b'new text\n';path.write_bytes(data);self.p['final_files'][self.cid]['sha256']=digest(data);self.assertIn('FINAL_MISMATCH',self.codes(True))
 def test_missing_final(self):self.p['final_files']={};self.assertIn('FINAL_MISSING',self.codes(True));self.assertEqual(self.score(True)['delivery_gate'],'REVIEW')
 def test_portfolio_count(self):self.p['base']['company_case_count']=2;self.assertIn('PORTFOLIO',self.codes())
 def test_portfolio_omission(self):self.p['portfolio']=[{'project_id':'other','category_id':self.cid}];self.assertIn('PORTFOLIO',self.codes())
 def test_media_manifest(self):self.p['base']['media']=[{'kind':'video','format':'mp4','bytes':1}];self.assertIn('MEDIA_MANIFEST',self.codes())
 def test_fake_mp4(self):
  if not shutil.which('ffprobe'):self.skipTest('ffprobe not installed')
  (self.root/'bad.mp4').write_bytes(b'x');self.p['base']['media']=[{'kind':'video','format':'mp4','bytes':1}];self.p['media_files']=[{'path':'bad.mp4','sha256':digest(b'x')}];self.assertIn('MEDIA_BYTES',self.codes())
 def test_legacy_migrate(self):self.assertEqual(audit(self.p['base'],self.root)['status'],'REVIEW')
 def test_duplicate_json(self):
  with self.assertRaises(ValueError):strict_json('{"a":1,"a":2}')
 def test_nan(self):
  with self.assertRaises(ValueError):strict_json('{"a":NaN}')
 def test_high_rights_fail(self):self.p['base']['human_checks']['rights']=False;self.assertEqual(self.score(True)['value'],'BLOCKED')
 def test_no_unsupported_id(self):self.p['assessments'][self.cid]['dimensions'][next(iter(CAT[self.cid]['weights']))]['support']=['imaginary'];self.assertLess(self.score(True)['weight_coverage'],100)
 def test_legacy_unknown_fields(self):self.p['base']['hidden_draft']='extra';self.assertIn('UNREVIEWED_FIELDS',self.codes())
 def test_dimension_zero_required(self):
  # Rubric coverage invariant: zero-weight dimension is still explicitly represented in profiles.
  self.assertTrue(any(x['weight']==0 for x in PROFILES['technology-01']['dimensions']))
if __name__=='__main__':unittest.main()
