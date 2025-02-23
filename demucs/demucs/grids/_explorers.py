# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.
from dora import Explorer
import treetable as tt


class MyExplorer(Explorer):
    test_metrics = ['nsdr', 'sdr_med']

    def get_grid_metrics(self):
        """Return the metrics that should be displayed in the tracking table.
        """
        return [
            tt.group("train", [
                tt.leaf("epoch"),
                tt.leaf("reco", ".3f"),
             ], align=">"),
            tt.group("valid", [
                tt.leaf("penalty", ".1f"),
                tt.leaf("ms", ".1f"),
                tt.leaf("reco", ".2%"),
                tt.leaf("breco", ".2%"),
                tt.leaf("b_nsdr", ".2f"),
                # tt.leaf("b_nsdr_drums", ".2f"),
                # tt.leaf("b_nsdr_bass", ".2f"),
                # tt.leaf("b_nsdr_other", ".2f"),
                # tt.leaf("b_nsdr_vocals", ".2f"),
             ], align=">"),
            tt.group("test", [
                tt.leaf(name, ".2f")
                for name in self.test_metrics
             ], align=">")
        ]

    def process_history(self, history):
        train = {
            'epoch': len(history),
        }
        valid = {}
        test = {}
        best_v_main = float('inf')
        breco = float('inf')
        for metrics in history:
            train.update(metrics['train'])
            valid.update(metrics['valid'])
            if 'main' in metrics['valid']:
                best_v_main = min(best_v_main, metrics['valid']['main']['loss'])
            valid['bmain'] = best_v_main
            valid['breco'] = min(breco, metrics['valid']['reco'])
            breco = valid['breco']
            if (metrics['valid']['loss'] == metrics['valid']['best'] or
                    metrics['valid'].get('nsdr') == metrics['valid']['best']):
                for k, v in metrics['valid'].items():
                    if k.startswith('reco_'):
                        valid['b_' + k[len('reco_'):]] = v
                    if k.startswith('nsdr'):
                        valid[f'b_{k}'] = v
            if 'test' in metrics:
                test.update(metrics['test'])
            metrics = history[-1]
        return {"train": train, "valid": valid, "test": test}
