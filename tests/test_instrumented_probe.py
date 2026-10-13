import unittest
from verification.direct_reference.instrumented_probe import (
    CASES, origin, permitted_navigation, post_descriptors, post_metadata, qualify, safe_path, request_failure,
)


class ProbeContract(unittest.TestCase):
    def test_frozen_routes(self):
        self.assertEqual(len(CASES), 5)
        for _, _, url in CASES.values():
            self.assertTrue(permitted_navigation(url, url))
            self.assertFalse(permitted_navigation(url + '&other=1', url))
        with self.assertRaises(ValueError):
            origin('https://user:secret@example.com/')

    def test_salford_exact_redirect_only(self):
        old = CASES['salford'][2]
        new = 'https://salfordcitycouncil.my.site.com/pr/s/planning-application/a0kSq000008OfVFIA0/pa20251084?c__r=Arcus_BE_Public_Register'
        self.assertTrue(permitted_navigation(new, old))
        self.assertFalse(permitted_navigation(new.replace('a0kSq000008OfVFIA0', 'wrong'), old))

    def test_trafford_bootstrap_only(self):
        frozen=CASES['trafford'][2]
        self.assertTrue(permitted_navigation('https://pa.trafford.gov.uk/online-applications/', frozen))
        self.assertFalse(permitted_navigation('https://pa.trafford.gov.uk/online-applications/search.do', frozen))

    def test_missing_is_not_blank(self):
        exact, fields = qualify([('Reference', 'R'), ('Status', 'Recommendation Made')], 'R')
        self.assertTrue(exact)
        self.assertEqual(fields['decision']['state'], 'NOT_PRESENT')
        self.assertEqual(qualify([('Decision','')], 'R')[1]['decision']['state'], 'PRESENT_BLANK')

    def test_duplicate_and_wrong_reference(self):
        self.assertFalse(qualify([('Reference','WRONG')], 'R')[0])
        exact, fields = qualify([('Reference','R'),('Reference','R')], 'R')
        self.assertFalse(exact)
        self.assertEqual(fields['reference']['state'], 'CONFLICTING')

    def test_metadata_redaction(self):
        from urllib.parse import urlencode
        import json
        body = urlencode({'message':json.dumps({'actions':[{'descriptor':'apex://Public/ACTION$get', 'params':{'token':'SECRET'}}]}),'aura.token':'SECRET'})
        self.assertEqual(post_descriptors(body), ['apex://Public/ACTION$get'])
        self.assertNotIn('SECRET', safe_path('https://example.com/pr/sfsites/a/SECRET?token=SECRET'))
        self.assertEqual(post_descriptors('message=bad'), [])
        metadata=post_metadata(body, CASES['manchester'][2])
        self.assertNotIn('SECRET', json.dumps(metadata))
        self.assertEqual(metadata[0]['token_state'], 'PRESENT_NOT_RETAINED')

    def test_each_redirect_destination_checked(self):
        url = CASES['manchester'][2]
        self.assertEqual(request_failure('https://other.example/resource', 'GET', 'Script', url, 2), 'UNADMITTED_ORIGIN')
        self.assertIsNone(request_failure(url, 'GET', 'Document', url, 1))

    def test_bounds_and_methods(self):
        url = CASES['manchester'][2]
        self.assertEqual(request_failure(url, 'GET', 'Document', url, 81), 'REQUEST_LIMIT')
        self.assertEqual(request_failure(url, 'POST', 'Fetch', url, 2), 'UNREVIEWED_METHOD')
        self.assertEqual(request_failure(url.replace('007GOmF', 'WRONG'), 'GET', 'Document', url, 2), 'UNADMITTED_NAVIGATION')

    def test_document_paths_before_dispatch(self):
        url = CASES['manchester'][2]
        for path in ['/sfc/servlet.shepherd/version/download/X', '/servlet/servlet.FileDownload?file=X', '/file.pdf']:
            self.assertEqual(request_failure(origin(url)+path, 'GET', 'Fetch', url, 2), 'DOCUMENT_DENIED')
        self.assertIsNone(request_failure(origin(url)+'/pr/s/sfsites/l/framework.js?label=download', 'GET', 'Script', url, 2))


    def test_guest_envelope_exact_read_only(self):
        import json
        from urllib.parse import urlencode, urlsplit
        from verification.direct_reference.arcus_http_probe import guest_envelope
        destination=CASES['manchester'][2]
        u=urlsplit(destination)
        action={'id':'1;a','descriptor':'aura://ApexActionController/ACTION$execute','params':{
            'namespace':'arcuscommunity','classname':'PublicRegisterViewService','method':'getRecordHeaderDetails',
            'params':{'recordId':u.path.rsplit('/',1)[-1],'registerName':'Arcus_BE_Public_Register'}}}
        form={'message':json.dumps({'actions':[action]}),'aura.token':'null',
              'aura.context':json.dumps({'mode':'PROD','globals':{}}),'aura.pageURI':u.path+'?'+u.query}
        body=urlencode(form)
        self.assertEqual(guest_envelope(body,destination),body)
        for change in ({'aura.token':'SECRET'}, {'message':json.dumps({'actions':[action,action]})},
                       {'aura.pageURI':'/other'}, {'aura.context':'{"globals":{"secret":"x"}}'}):
            with self.assertRaises(ValueError):
                guest_envelope(urlencode(dict(form,**change)),destination)
        action['params']['params']['recordId']='WRONG'
        with self.assertRaises(ValueError):
            guest_envelope(urlencode(dict(form,message=json.dumps({'actions':[action]}))),destination)

    def test_guest_response_retains_only_planning_values(self):
        import json
        from verification.direct_reference.arcus_http_probe import response_summary
        data={'actions':[{'state':'SUCCESS','returnValue':[
            {'label':'Reference','value':'R'}, {'label':'Status','value':'Final'},
            {'label':'Applicant','value':'PRIVATE_PERSON'}]}]}
        result=response_summary(data,'R')
        self.assertTrue(result['exact_reference_value_present'])
        self.assertNotIn('PRIVATE_PERSON',json.dumps(result))
        self.assertNotIn('Applicant',json.dumps(result))
        self.assertEqual(result['planning_label_values'],[['Reference','R'],['Status','Final']])


if __name__ == '__main__':
    unittest.main()
