import unittest
from pathlib import Path

from runner.config import load_protocol
from runner.protocol import replay, time_grid


PACKAGE = Path(__file__).resolve().parents[1]
PROTOCOL = PACKAGE / 'config' / 'protocol-ca1p5e4-r2.toml'


class R2ProtocolContracts(unittest.TestCase):
    def protocol(self):
        return load_protocol(PROTOCOL)

    def test_frozen_r2_values(self):
        p = self.protocol()
        self.assertEqual(p['name'], 'GW-Ca1p5e4-R2-v1')
        self.assertEqual(p['physics']['capillary_number'], 0.00015)
        self.assertEqual(p['physics']['rhoA'], 0.10)
        self.assertEqual(p['physics']['rhoB'], 0.10)
        self.assertEqual(p['physics']['tauA'], 0.78)
        self.assertEqual(p['physics']['tauB'], 0.92)
        self.assertEqual(p['physics']['alpha'], 0.009)
        self.assertEqual(p['physics']['beta'], 0.90)
        self.assertEqual(p['physics']['affinity'], 0.2588190451)
        self.assertEqual(p['domain']['bc'], 4)
        self.assertEqual(p['domain']['reservoir_layers'], 3)
        self.assertEqual(p['stopping']['check_pvi'], 0.1)
        self.assertEqual(p['stopping']['window_points'], 5)
        self.assertEqual(p['stopping']['max_pvi'], 3.6)
        self.assertEqual(p['stopping']['standard'], {
            'start_pvi': 0.5,
            'max_dsg': 0.0030,
            'range_sg': 0.0060,
            'max_flip': 0.0100,
            'consecutive': 4,
        })
        self.assertEqual(p['stopping']['accepted'], {
            'start_pvi': 3.0,
            'max_dsg': 0.008,
            'range_sg': 0.025,
            'max_flip': 0.030,
            'consecutive': 3,
        })

    def test_r2_time_grid(self):
        grid = time_grid(self.protocol())
        self.assertEqual(grid['checkpoint_steps'], 22124)
        self.assertEqual(grid['max_steps'], 796464)
        self.assertEqual(grid['max_checkpoints'], 36)

    def test_r2_earliest_standard_is_checkpoint_8(self):
        rows = [{'index': i, 'sg': 0.2, 'flip': 0.0} for i in range(1, 37)]
        decision = replay(rows, self.protocol())
        self.assertEqual((decision['index'], decision['reason']), (8, 'STANDARD'))

    def test_r2_accepted_contract_unchanged(self):
        p = self.protocol()
        accepted = p['stopping']['accepted']
        self.assertEqual((accepted['start_pvi'], accepted['max_dsg'], accepted['range_sg'],
                          accepted['max_flip'], accepted['consecutive']),
                         (3.0, 0.008, 0.025, 0.030, 3))

    def test_r2_cap_is_checkpoint_36_when_not_converged(self):
        rows = [{'index': i, 'sg': 0.1 if i % 2 else 0.8, 'flip': 0.7}
                for i in range(1, 37)]
        decision = replay(rows, self.protocol())
        self.assertEqual((decision['index'], decision['reason']), (36, 'CAP_REACHED'))


if __name__ == '__main__':
    unittest.main()
