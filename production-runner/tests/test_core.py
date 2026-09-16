import importlib
import tempfile
import unittest
from pathlib import Path

class CoreContracts(unittest.TestCase):
    def mod(self, name):
        spec = importlib.util.find_spec('runner.' + name)
        self.assertIsNotNone(spec, 'implementation missing: ' + name)
        return importlib.import_module('runner.' + name)

    def test_even_timestep_and_cap(self):
        p = self.mod('protocol')
        cfg = p.default_protocol()
        grid = p.time_grid(cfg)
        self.assertEqual(grid['checkpoint_steps'], 16592)
        self.assertEqual(grid['max_steps'], 663680)
        self.assertEqual(grid['max_checkpoints'], 40)

    def test_standard_first_stop_is_15(self):
        p = self.mod('protocol')
        rows = [{'index':i, 'sg':.2, 'flip':0.0} for i in range(1,41)]
        res = p.replay(rows, p.default_protocol())
        self.assertEqual((res['index'],res['reason']), (15,'STANDARD'))

    def test_accepted_not_before_32(self):
        p = self.mod('protocol')
        rows = [{'index':i, 'sg':.2 + .001*(i%2), 'flip':.002} for i in range(1,41)]
        res = p.replay(rows, p.default_protocol())
        self.assertEqual((res['index'],res['reason']), (32,'ACCEPTED'))

    def test_cap_not_convergence(self):
        p = self.mod('protocol')
        rows = [{'index':i, 'sg':.1 if i%2 else .8, 'flip':.7} for i in range(1,41)]
        self.assertEqual(p.replay(rows,p.default_protocol())['reason'],'CAP_REACHED')

    def test_replay_rejects_missing_checkpoint(self):
        p = self.mod('protocol')
        with self.assertRaises(ValueError):
            p.replay([{'index':1,'sg':.2,'flip':0}, {'index':3,'sg':.2,'flip':0}],p.default_protocol())

    def test_config_precedence_and_relative_path(self):
        c = self.mod('config')
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/'machine.toml'
            f.write_text('[paths]\nraw_root="rocks"\noutput_root="data"\n[runtime]\nmax_jobs=3\n')
            obj=c.load_machine(f, {'runtime.max_jobs':7}, {'LBPM_RUNNER_MAX_JOBS':'5'})
            self.assertEqual(obj['runtime']['max_jobs'],7)
            self.assertEqual(obj['paths']['raw_root'],str(Path(td)/'rocks'))

    def test_config_typo_rejected(self):
        c = self.mod('config')
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/'m.toml'; f.write_text('[runtime]\nmax_job=8\n')
            with self.assertRaises(ValueError): c.load_machine(f,{}, {})

    def test_atomic_json(self):
        u=self.mod('util')
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/'a.json'; u.atomic_json(f, {'n':1})
            self.assertEqual(u.read_json(f)['n'],1)
            self.assertEqual([p.name for p in Path(td).iterdir()],['a.json'])

    def test_archive_roundtrip_and_restore(self):
        a=self.mod('archive')
        with tempfile.TemporaryDirectory() as td:
            d=Path(td)/'attempt'; d.mkdir()
            source={f'id_t{i}.raw':(bytes([0,1,2])*5000+bytes([i])) for i in [2,4,6]}
            for name,b in source.items(): (d/name).write_bytes(b)
            m=a.archive_attempt(d, release=True)
            self.assertTrue(m['verified'])
            self.assertFalse(list(d.glob('id_t*.raw')))
            target=Path(td)/'restore'; a.restore_attempt(d,target)
            self.assertEqual({p.name:p.read_bytes() for p in target.glob('*.raw')},source)

    def test_archive_corruption_never_deletes_raw(self):
        a=self.mod('archive')
        with tempfile.TemporaryDirectory() as td:
            d=Path(td)/'attempt'; d.mkdir(); raw=d/'id_t2.raw'; raw.write_bytes(b'012'*500)
            a.archive_attempt(d, release=False)
            (d/'checkpoints.tar.zst').write_bytes(b'broken')
            with self.assertRaises(Exception): a.archive_attempt(d, release=True)
            self.assertTrue(raw.exists())

    def test_archive_manifest_rejects_traversal(self):
        a=self.mod('archive')
        with self.assertRaises(ValueError): a.safe_member('../outside')

    def test_disk_hysteresis(self):
        a=self.mod('archive')
        self.assertTrue(a.pressure(9,False,10,15))
        self.assertTrue(a.pressure(12,True,10,15))
        self.assertFalse(a.pressure(16,True,10,15))

if __name__=='__main__': unittest.main()
