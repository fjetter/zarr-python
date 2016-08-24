# -*- coding: utf-8 -*-
from __future__ import absolute_import, print_function, division


import numpy as np


from zarr.meta import encode_dtype, decode_dtype


filter_registry = dict()


class DeltaFilter(object):

    canonical_name = 'delta'

    def __init__(self, enc_dtype, dec_dtype):
        self.enc_dtype = enc_dtype
        self.dec_dtype = dec_dtype

    def encode(self, arr):
        # ensure 1D array
        arr = np.asarray(arr).reshape(-1)
        # setup encoded output
        enc = np.empty_like(arr, dtype=self.enc_dtype)
        # set first element
        enc[0] = arr[0]
        # compute differences
        enc[1:] = np.diff(arr)
        return enc

    def decode(self, buf):
        # interpret buffer as array
        enc = np.frombuffer(buf, dtype=self.enc_dtype)
        # setup decoded output
        dec = np.empty_like(enc, dtype=self.dec_dtype)
        # decode differences
        np.cumsum(enc, out=dec)
        return dec

    def get_config(self):
        config = dict()
        config['name'] = self.canonical_name
        config['enc_dtype'] = encode_dtype(self.enc_dtype)
        config['dec_dtype'] = encode_dtype(self.dec_dtype)
        return config

    @classmethod
    def from_config(cls, config):
        enc_dtype = decode_dtype(config['enc_dtype'])
        dec_dtype = decode_dtype(config['dec_dtype'])
        return cls(enc_dtype=enc_dtype, dec_dtype=dec_dtype)


filter_registry[DeltaFilter.canonical_name] = DeltaFilter


class ScaleOffsetFilter(object):

    canonical_name = 'scaleoffset'

    def __init__(self, offset, scale, enc_dtype, dec_dtype):
        self.offset = offset
        self.scale = scale
        self.enc_dtype = enc_dtype
        self.dec_dtype = dec_dtype

    def encode(self, arr):
        # ensure 1D array
        arr = np.asarray(arr).reshape(-1)
        # compute scale offset
        enc = ((arr - self.offset) / self.scale).astype(self.enc_dtype)
        return enc

    def decode(self, buf):
        # interpret buffer as array
        enc = np.frombuffer(buf, dtype=self.enc_dtype)
        # decode scale offset
        dec = ((enc * self.scale) + self.offset).astype(self.dec_dtype)
        return dec

    def get_config(self):
        config = dict()
        config['name'] = self.canonical_name
        config['enc_dtype'] = encode_dtype(self.enc_dtype)
        config['dec_dtype'] = encode_dtype(self.dec_dtype)
        config['scale'] = self.scale
        config['offset'] = self.offset
        return config

    @classmethod
    def from_config(cls, config):
        enc_dtype = decode_dtype(config['enc_dtype'])
        dec_dtype = decode_dtype(config['dec_dtype'])
        scale = config['scale']
        offset = config['offset']
        return cls(enc_dtype=enc_dtype, dec_dtype=dec_dtype, scale=scale,
                   offset=offset)


filter_registry[ScaleOffsetFilter.canonical_name] = ScaleOffsetFilter