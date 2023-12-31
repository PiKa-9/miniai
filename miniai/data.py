# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/#data.ipynb.

# %% auto 0
__all__ = ['Dataset', 'DataLoaders']

# %% ../nbs/#data.ipynb 1
import fastcore.all as fc

# %% ../nbs/#data.ipynb 2
class Dataset():
    def __init__(self, x, y): self.x = x; self.y = y
    def __getitem__(self, idx): return (self.x[idx], self.y[idx])
    def __len__(self): return len(self.y)

# %% ../nbs/#data.ipynb 3
class DataLoaders:
    def __init__(self, train, valid): fc.store_attr()
