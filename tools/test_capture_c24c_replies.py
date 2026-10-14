import unittest
from unittest.mock import patch
import capture_c24c_replies as capture


class CaptureGuardTests(unittest.TestCase):
    def test_idle_guard_refuses_missing_or_unsafe_state(self):
        baseline = {k:False for k in ('owned','active','stopped','releasing','release_failed')}
        capture.require_idle(baseline)
        for key in baseline:
            with self.subTest(key=key):
                with self.assertRaises(RuntimeError):
                    capture.require_idle({**baseline,key:True})
                with self.assertRaises(RuntimeError):
                    capture.require_idle({k:v for k,v in baseline.items() if k!=key})

    def test_binding_and_live_video_are_required(self):
        row={'deviceid':capture.PHONE,'pid':'C24C','uid':'C24CBFBD','receiver_name':'iMouse2-C24C','state':1}
        capture.verify_device(row)
        for key, value in [('deviceid',capture.OTHER),('pid','C241'),('uid','wrong'),
                           ('receiver_name','iMouse2-C241'),('state',0)]:
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                capture.verify_device({**row,key:value})

    def test_protocol_refusal_is_not_retried(self):
        import io
        response=io.BytesIO(b'{"status":200,"data":{"code":409,"message":"owned"}}')
        with patch.object(capture.urllib.request,'urlopen',return_value=response) as open_url:
            with self.assertRaises(RuntimeError):
                capture.request(data={'fun':'/input/acquire','data':{'id':capture.PHONE}})
            self.assertEqual(open_url.call_count,1)


if __name__=='__main__':
    unittest.main()
