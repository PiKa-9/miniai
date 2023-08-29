# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/#learner.ipynb.

# %% auto 0
__all__ = ['Learner', 'TrainLearner', 'MomentumLearner', 'summary', 'show_batch_images']

# %% ../nbs/#learner.ipynb 1
import torch, torch.nn as nn, torch.nn.functional as F
from torch import tensor, optim
import numpy as np, pandas as pd, matplotlib.pyplot as plt, matplotlib as mpl, math
import fastcore.all as fc
from operator import attrgetter
from collections.abc import Mapping
from functools import partial
from .callbacks import *
from .hooks import Hooks

# %% ../nbs/#learner.ipynb 9
class Learner:
    def __init__(self, dls, model, loss_func, opt_func=optim.Adam, lr=None, cbs=[]): 
        fc.store_attr()
        
    @with_cbs('batch')
    def _one_batch(self):
        # Get the gradients by calculating the loss
        self.predict()
        self.get_loss()
        # Update the weights
        if self.training:
            self.backward()
            self.step()
            self.zero_grad()
            
    @with_cbs('epoch')
    def _one_epoch(self):
        for self.batch_iter, self.batch in enumerate(self.dl): self._one_batch()
    
    @with_cbs('fit')
    def _fit(self):
        for self.epoch in self.epochs:
            self.one_epoch(True)
            with torch.no_grad(): self.one_epoch(False)
    
    def one_epoch(self, train):
        self.model.train(train)
        self.training = train
        self.dl = self.dls.train if train else self.dls.valid
        self._one_epoch()

    def fit(self, epochs, lr=None, cbs=None):
        if (lr != None): self.lr = lr
        if (cbs != None): orig_cbs = self.cbs; self.cbs = cbs
        self.opt = self.opt_func(self.model.parameters(), self.lr)
        self.epochs = range(epochs)
        self._fit()
        if (cbs != None): self.cbs = orig_cbs
            
    def callback(self, method_nm): run_cbs(self.cbs, method_nm, self)
        
    def __getattr__(self, nm):
        if nm in ['predict', 'get_loss', 'backward', 'step', 'zero_grad']: return partial(self.callback, nm)
        raise AttributeError(nm)
    
    def lr_find(self, start_lr=1e-7, coef=1.3):
        lr_finder = LRFinderCB(coef)
        self.fit(1, start_lr, cbs=[TrainCB(), lr_finder, MetricCB(), ProgressCB()])
        lr_finder.plot();

# %% ../nbs/#learner.ipynb 10
class TrainLearner(Learner):
    def predict(self): self.preds = self.model(self.batch[0])
    def get_loss(self): self.loss = self.loss_func(self.preds, self.batch[1])
    def backward(self): self.loss.backward()
    def step(self): self.opt.step()
    def zero_grad(self): self.opt.zero_grad()

# %% ../nbs/#learner.ipynb 11
class MomentumLearner(TrainLearner):
    def __init__(self, dls, model, loss_func, opt=optim.Adam, lr=None, cbs=[], mom=0.85):
        super(TrainLearner, self).__init__(dls, model, loss_func, opt_func=opt, lr=lr, cbs=cbs)
        self.mom = mom

    def zero_grad(self): 
        with torch.no_grad():
            for p in self.model.parameters(): p.grad = p.grad*self.mom

# %% ../nbs/#learner.ipynb 17
def _flops(x, h, w):
    if x.dim()<3: return x.numel()
    if x.dim()==4: return x.numel()*h*w
    
@fc.patch
def summary(self:Learner):
        res = f'|Module|Input shape|Output shape|Param count|MFLOPS|\n|--|--|--|--|--|\n'
        total_params = 0; total_MFLOPS = 0
        def _get_summary(hook, mod, inp, out):
            nonlocal res, total_params, total_MFLOPS
            param_cnt = 0; flops = 0
            for p in mod.parameters():
                param_cnt += torch.numel(p)
                flops += _flops(p, out.shape[-2], out.shape[-1])
            flops /= 1e6
            res += f'|{type(mod).__name__:14}|{str(list(inp[0].shape)):20}|{str(list(out.shape)):16}|{param_cnt}|{flops:.1f}|\n'
            total_params += param_cnt; total_MFLOPS += flops
        with Hooks(self.model, _get_summary) as hooks: self.model(next(iter(self.dls.train))[0])
        if fc.IN_NOTEBOOK:
            from IPython.display import Markdown
            return Markdown(res + f'|--|--|--|{total_params}|{total_MFLOPS:.1f}|\n')
        else: print(res + f'|--|--|--|{total_params}|{total_MFLOPS:1.f}|\n')

# %% ../nbs/#learner.ipynb 18
@fc.patch
def show_batch_images(self:Learner, n=None, **kwargs):
    batch = next(iter(self.dls.train))
    if n is None: n = batch[0].shape[0]
    show_images(batch[0][:n], titles=batch[1].tolist(), **kwargs);
