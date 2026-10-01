"""Bounded GitHub expression-context regression for this manual workflow.

GitHub Contexts reference: jobs.<job_id>.env excludes job; step env includes it.
Fail closed on any expression outside the exact reviewed locations/values.
This is not a general Actions validator; hosted validation remains authoritative.
"""
import re
import unittest
from pathlib import Path
import yaml

P=Path(__file__).parent

def validate(workflow):
    if set(workflow['on']) != {'workflow_dispatch'}: raise ValueError('Nonmanual trigger')
    job=workflow['jobs']['rehearse']
    if 'AH_SERVICE_ID' in job.get('env',{}): raise ValueError('Service context at job level')
    allowed={('job.services.postgres.id','env'),('github.sha','with'),('runner.temp','with')}
    seen=[]
    # Step leaf paths have six components: jobs/rehearse/steps/index/env/key.
    def adapt_walk(value,path=()):
        if isinstance(value,dict):
            for k,v in value.items():adapt_walk(v,path+(str(k),))
        elif isinstance(value,list):
            for i,v in enumerate(value):adapt_walk(v,path+(str(i),))
        elif isinstance(value,str):
            for expr in re.findall(r'\$\{\{\s*(.*?)\s*\}\}',value):
                if len(path)!=6 or path[:3]!=('jobs','rehearse','steps') or (expr,path[-2]) not in allowed:
                    raise ValueError('Unsupported expression context: '+'.'.join(path))
                seen.append(expr)
    adapt_walk(workflow)
    if sorted(seen)!=sorted(['job.services.postgres.id']*3+['github.sha','runner.temp']):raise ValueError('Expression inventory changed')
    for step in job['steps']:
        if '$AH_SERVICE_ID' in step.get('run','') or 'validate_environment' in step.get('run','') or 'native_rehearsal ' in step.get('run',''):
            if step.get('env',{}).get('AH_SERVICE_ID')!='${{ job.services.postgres.id }}':raise ValueError('Missing step service identity')
        if 'if' in step and step['if']!='always()':raise ValueError('Unexpected conditional')
    return True

class ContextTests(unittest.TestCase):
    def setUp(self):self.w=yaml.load((P/'native-postgres.workflow.yml').read_text(),Loader=yaml.BaseLoader)
    def test_all_expression_locations(self):self.assertTrue(validate(self.w))
    def test_original_failure_rejected(self):
        self.w['jobs']['rehearse']['env']['AH_SERVICE_ID']='${{ job.services.postgres.id }}'
        with self.assertRaises(ValueError):validate(self.w)
    def test_unreviewed_context_rejected(self):
        self.w['jobs']['rehearse']['steps'][0]['with']['x']='${{ secrets.PRODUCTION }}'
        with self.assertRaises(ValueError):validate(self.w)
    def test_trigger_change_rejected(self):
        self.w['on']['push']=None
        with self.assertRaises(ValueError):validate(self.w)
    def test_workflow_copies_identical(self):
        self.assertEqual((P/'native-postgres.workflow.yml').read_bytes(),(P.parents[1]/'.github/workflows/ah-native-postgres.yml').read_bytes())

if __name__=='__main__':unittest.main()
