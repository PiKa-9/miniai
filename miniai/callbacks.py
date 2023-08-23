# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/#callbacks.ipynb.

# %% auto 0
__all__ = ['def_device', 'to_cpu', 'run_cbs', 'CancelFitException', 'CancelEpochException', 'CancelBatchException', 'with_cbs',
           'Callback', 'to_device', 'DeviceCB', 'TrainCB', 'MetricCB', 'ProgressCB', 'LRFinderCB', 'BaseSchedCB',
           'BatchSchedCB', 'RecorderCB']

# %% ../nbs/#callbacks.ipynb 1
import torch, torch.nn as nn, torch.nn.functional as F
from torch import tensor, optim
import numpy as np, pandas as pd, matplotlib.pyplot as plt, matplotlib as mpl, math
import fastcore.all as fc
from operator import attrgetter
from collections.abc import Mapping
from functools import partial
from fastprogress import progress_bar, master_bar
from torcheval.metrics import Mean
from .plotting import subplots

# %% ../nbs/#callbacks.ipynb 2
# Since there were some problems with torcheval metrics when tensors which are on GPU
def to_cpu(x):
    if isinstance(x, Mapping): return {k:to_cpu(v) for k,v in x.items()}
    if isinstance(x, list): return [to_cpu(o) for o in x]
    if isinstance(x, tuple): return tuple(to_cpu(list(x)))
    res = x.detach().cpu()
    return res.float() if res.dtype==torch.float16 else res

# %% ../nbs/#callbacks.ipynb 3
def run_cbs(cbs, method_nm, learn=None):
    for cb in sorted(cbs, key=attrgetter('order')):
        method = getattr(cb, method_nm, None)
        if method is not None: method(learn)

# %% ../nbs/#callbacks.ipynb 4
class CancelFitException(Exception): pass
class CancelEpochException(Exception): pass
class CancelBatchException(Exception): pass

class with_cbs:
    def __init__(self, cb_nm): self.cb_nm = cb_nm
    def __call__(self, f):
        def _f(o, *args, **kwargs):
            try:
                o.callback(f'before_{self.cb_nm}')
                f(o, *args, **kwargs)
                o.callback(f'after_{self.cb_nm}')
            except globals()[f'Cancel{self.cb_nm.title()}Exception']: pass
        return _f

# %% ../nbs/#callbacks.ipynb 5
class Callback(): 
    order = 0

# %% ../nbs/#callbacks.ipynb 6
def_device = 'cuda' if torch.cuda.is_available() else 'cpu'

def to_device(x, device=def_device):
    if isinstance(x, torch.Tensor): return x.to(device)
    if isinstance(x, Mapping): return {k:v.to(device) for k,v in x.items()}
    return type(x)(to_device(o, device) for o in x)

class DeviceCB(Callback):
    def __init__(self, device=def_device): self.device=device
    def before_fit(self, learn): 
        if hasattr(learn.model, 'to'): learn.model.to(self.device)
    def before_batch(self, learn): to_device(learn.batch, self.device)

# %% ../nbs/#callbacks.ipynb 7
class TrainCB(Callback):
    order = 0
    def predict(self, learn): learn.preds = learn.model(learn.batch[0])
    def get_loss(self, learn): learn.loss = learn.loss_func(learn.preds, learn.batch[1])
    def backward(self, learn): learn.loss.backward()
    def step(self, learn): learn.opt.step()
    def zero_grad(self, learn): learn.opt.zero_grad()

# %% ../nbs/#callbacks.ipynb 8
class MetricCB(Callback):
    order = TrainCB.order+1
    def __init__(self, include_train=False, **kwargs): 
        self.include_train = include_train; self.metric_list = kwargs; self.loss = Mean()
        
    def before_fit(self, learn): learn.metrics = self
    def before_epoch(self, learn): 
        if self.include_train or (not learn.training):
            for metric in self.metric_list.values(): metric.reset()
        self.loss.reset()
    
    def after_batch(self, learn): 
        cpu_preds = to_cpu(learn.preds); cpu_y_b = to_cpu(learn.batch[1])
        if self.include_train or (not learn.training):
            for metric in self.metric_list.values(): metric.update(cpu_preds, cpu_y_b)
        self.loss.update(to_cpu(learn.loss), weight=len(cpu_y_b))
    def after_epoch(self, learn):
        if learn.training: 
            self.log = {}
            self.log['epoch'] = learn.epoch
            self.log['train_loss'] = round(float(self.loss.compute()), 3)
            if self.include_train:
                for metric_nm in self.metric_list:
                    self.log[f'train_{metric_nm}'] = round(float(self.metric_list[metric_nm].compute()), 3)
        else: 
            prefix = 'valid_' if self.include_train else ''
            self.log['valid_loss'] = round(float(self.loss.compute()), 3)
            for metric_nm in self.metric_list:
                self.log[f'{prefix}{metric_nm}'] = round(float(self.metric_list[metric_nm].compute()), 3)
            self._log(self.log)
    
    def _log(self, d):
        print(d)

# %% ../nbs/#callbacks.ipynb 9
class ProgressCB(Callback):
    order = MetricCB.order+1
    def _log(self, d):
        if self.first:
            self.mbar.write(list(d), table=True)
            self.first = False
        self.mbar.write(list(d.values()), table=True)
    
    def before_fit(self, learn):
        learn.epochs = self.mbar = master_bar(learn.epochs)
        self.first = True
        learn.metrics._log = self._log
    def before_epoch(self, learn): learn.dl = progress_bar(learn.dl, leave=False, parent=self.mbar)

# %% ../nbs/#callbacks.ipynb 10
class LRFinderCB(Callback):
    def __init__(self, coef=1.3): self.coef = coef; self.lrs = []; self.losses = []
    def before_fit(self, learn):
        self.lrs = []; self.losses = []; self.min_loss = math.inf
    def after_batch(self, learn):
        if not learn.training: raise CancelEpochException()
        loss = to_cpu(learn.loss)
        self.min_loss = min(self.min_loss, loss)
        if math.isnan(loss) or (3*self.min_loss < loss): raise CancelFitException()
        self.lrs.append(learn.opt.param_groups[0]['lr'])
        self.losses.append(loss)
        for p in learn.opt.param_groups: p['lr'] *= self.coef

    def plot(self):
        plt.plot(self.lrs, self.losses)
        plt.xscale('log')

# %% ../nbs/#callbacks.ipynb 11
class BaseSchedCB(Callback):
    def __init__(self, sched): self.sched = sched
    def before_fit(self, learn): self.schedo = self.sched(learn.opt)
    def step(self, learn):
        if learn.training: self.schedo.step()

class BatchSchedCB(BaseSchedCB):
    def after_batch(self, learn): 
        self.step(learn)

# %% ../nbs/#callbacks.ipynb 12
class RecorderCB(Callback):
    def __init__(self, **d): self.d = d
    def before_fit(self, learn):
        self.recs = {k:[] for k in self.d}
        self.pg = learn.opt.param_groups[0]
    def after_batch(self, learn):
        for k, v in self.d.items():
            self.recs[k].append(v(self.pg))
    def plot(self, **kwargs):
        fig, ax = subplots(n=len(self.d), **kwargs)
        for i, k in enumerate(self.d):
            ax[i].plot(self.recs[k], label=k)
            ax[i].legend()
        plt.tight_layout(); plt.show();
