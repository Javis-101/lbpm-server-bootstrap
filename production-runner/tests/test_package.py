import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]

class Package(unittest.TestCase):
    def test_reproducible_package_and_all_member_hashes(self):
        tool=ROOT/'tools/package.py'
        self.assertTrue(tool.is_file(),'reproducible builder missing')
        with tempfile.TemporaryDirectory() as td:
            outputs=[]
            for sub in ('one','two'):
                out=Path(td)/sub
                p=subprocess.run([sys.executable,str(tool),'--out',str(out)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
                self.assertEqual(p.returncode,0,p.stdout)
                outputs.append(next(out.glob('*.zip')))
            self.assertEqual(outputs[0].read_bytes(),outputs[1].read_bytes())
            with zipfile.ZipFile(outputs[0]) as z:
                self.assertIsNone(z.testzip())
                names=z.namelist(); prefix=names[0].split('/')[0]+'/'
                for line in z.read(prefix+'SHA256SUMS').decode().splitlines():
                    digest,name=line.split('  ',1)
                    self.assertEqual(hashlib.sha256(z.read(prefix+name)).hexdigest(),digest,name)
                self.assertIn(prefix+'runner/results.py',names)
                self.assertFalse(any('__pycache__' in name for name in names))

if __name__=='__main__': unittest.main()
