import copy, json, math, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'scripts'))
from legacy import CAT,RULES,audit,score,fees
class TestRules(unittest.TestCase):
 def setUp(self):
  self.p=json.loads((ROOT/'examples/strong.json').read_text()); self.root=ROOT/'examples/evidence'
 def run_audit(self): return audit(self.p,self.root)
 def codes(self): return {i['code'] for i in self.run_audit()['issues']}
 def test_catalog(self):
  self.assertEqual(len(CAT),95); self.assertEqual(sum(c['mode']=='nomination' for c in CAT.values()),12)
  self.assertTrue(all(sum(c['weights'].values())==100 for c in CAT.values() if c['weights']))
 def test_ai_weights(self): self.assertEqual(list(CAT['special-01']['weights'].values()),[10,20,35,35])
 def test_score(self): self.assertEqual(score('special-01',[10,0,0,0]),10)
 def test_product_weights(self): self.assertEqual(score('technology-01',[0,10,10,10]),100)
 def test_invalid_scores(self):
  for v in [-1,11,float('nan'),float('inf'),True,'9']:
   with self.subTest(v=v), self.assertRaises(ValueError): score('special-01',[v,1,1,1])
 def test_nomination_no_score(self):
  with self.assertRaises(ValueError): score('nomination_company-01',[9]*4)
 def test_fee(self): self.assertEqual(fees({'extra_certificate':1,'major':2,'excellent':1}),21360)
 def test_invalid_fees(self):
  for n in [-1,1.2,True]:
   with self.assertRaises(ValueError): fees({'major':n})
 def test_strong(self):
  x=self.run_audit(); self.assertEqual(x['status'],'INTERNAL_CHECKS_PASSED'); self.assertEqual(x['scores']['special-18']['value'],'CONDITIONAL'); self.assertIn('UNVERIFIED',x['official_submission'])
 def test_weak(self):
  self.p['scores']['special-18']=[4]*4; self.assertEqual(self.run_audit()['scores']['special-18']['value'],'NOT_RECOMMENDED')
 def test_unknown_evidence(self):
  self.p['human_checks']['evidence_sufficiency']=False; self.assertEqual(self.run_audit()['scores']['special-18']['value'],'INSUFFICIENT_EVIDENCE')
 def test_high_score_not_override(self):
  self.p['human_checks']['rights']=False; self.assertEqual(self.run_audit()['status'],'BLOCKED')
 def test_old_edition(self): self.p['edition']=17; self.assertIn('EDITION',self.codes())
 def test_start_date(self): self.p['start']='2026-03-19'; self.assertIn('DATE',self.codes())
 def test_reverse_date(self): self.p['start']='2026-06-01'; self.assertIn('DATE',self.codes())
 def test_missing_date(self): del self.p['start']; self.assertIn('DATE_UNKNOWN',self.codes())
 def test_duplicate(self): self.p['categories']*=2; self.assertIn('DUPLICATE',self.codes())
 def test_over_limit(self): self.p['categories']=['special-01','special-02','special-03']; self.assertIn('LIMIT',self.codes())
 def test_invalid_category(self): self.p['categories']=['unknown']; self.assertIn('CATEGORY_UNKNOWN',self.codes())
 def test_nomination(self): self.p['categories']=['nomination_team-01']; self.assertIn('NOMINATION',self.codes())
 def test_hash(self): self.p['facts'][0]['sha256']='0'*64; self.assertIn('BINDING',self.codes())
 def test_fake_quote(self): self.p['facts'][0]['quote']='行业第一'; self.assertIn('BINDING',self.codes())
 def test_fake_claim(self): self.p['facts'][0]['claim']='同比增长1000%'; self.assertIn('BINDING',self.codes())
 def test_path_traversal(self): self.p['facts'][0]['source']='../../README.md'; self.assertIn('BINDING',self.codes())
 def test_private(self): self.p['facts'][0]['public']=False; self.assertIn('FACT_PERMISSION_CONFLICT',self.codes())
 def test_conflict(self): self.p['facts'][0]['conflict']=True; self.assertIn('FACT_PERMISSION_CONFLICT',self.codes())
 def test_duplicate_fact(self): self.p['facts'].append(copy.deepcopy(self.p['facts'][0])); self.assertIn('FACT_ID',self.codes())
 def test_draft_injection(self): self.p['drafts']['special-18'][0]['text']+='行业第一'; self.assertIn('DRAFT_BINDING',self.codes())
 def test_empty_ledger(self): self.p['facts']=[]; self.assertIn('NO_FACTS',self.codes()); self.assertEqual(self.run_audit()['status'],'BLOCKED')
 def test_no_confirmation(self): del self.p['human_checks']['stamped_confirmation']; self.assertEqual(self.run_audit()['status'],'REVIEW')
 def test_anonymity(self): self.p['human_checks']['anonymity']=False; self.assertIn('ANONYMITY',self.codes())
 def test_av_limit(self): self.p['media']=[{'kind':'video','format':'mp4','bytes':100}]*6; self.assertIn('AV_COUNT',self.codes())
 def test_file_size(self): self.p['media']=[{'kind':'video','format':'mp4','bytes':100000001}]; self.assertIn('MEDIA_SPEC',self.codes())
 def test_jpg(self): self.p['media']=[{'kind':'image','format':'png'}]; self.assertIn('MEDIA_FORMAT',self.codes())
 def test_image_soft_limit(self): self.p['media']=[{'kind':'image','format':'jpg'}]*13; self.assertIn('IMAGE_COUNT',self.codes()); self.assertEqual(self.run_audit()['status'],'REVIEW')
 def test_company_limit(self): self.p['company_case_count']=21; self.assertIn('COMPANY_COUNT',self.codes())
 def test_no_override(self): self.p['override']='READY'; self.p['human_checks']['rights']=False; self.assertEqual(self.run_audit()['status'],'BLOCKED')
if __name__=='__main__': unittest.main()
