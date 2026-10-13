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


if __name__ == '__main__':
    unittest.main()
