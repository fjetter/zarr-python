# -*- coding: utf-8 -*-
from __future__ import absolute_import, print_function, division


from functools import reduce  # TODO PY2 compatibility
import operator
import itertools
import numpy as np


from zarr.blosc import compress, decompress
from zarr.util import is_total_slice, normalize_array_selection, \
    get_chunk_range


class Array(object):

    def __init__(self, store):
        """Instantiate an array.

        Parameters
        ----------
        store : zarr.store.base.ArrayStore
            Array store.

        """
        self._store = store

        # configuration metadata
        self._shape = store.meta['shape']
        self._chunks = store.meta['chunks']
        self._dtype = store.meta['dtype']
        self._cname = store.meta['cname']
        self._clevel = store.meta['clevel']
        self._shuffle = store.meta['shuffle']
        self._fill_value = store.meta['fill_value']

        # user-defined attributes
        self._attrs = store.attrs

    @property
    def shape(self):
        return self._shape

    @property
    def chunks(self):
        return self._chunks

    @property
    def dtype(self):
        return self._dtype

    @property
    def cname(self):
        return self._cname

    @property
    def clevel(self):
        return self._clevel

    @property
    def shuffle(self):
        return self._shuffle

    @property
    def fill_value(self):
        return self._fill_value

    @property
    def attrs(self):
        return self._attrs

    @property
    def cbytes(self):
        # pass through
        return self._store.cbytes

    @property
    def initialized(self):
        # pass through
        return self._store.initialized

    # derived properties

    @property
    def size(self):
        return reduce(operator.mul, self._shape)

    @property
    def itemsize(self):
        return self._dtype.itemsize

    @property
    def nbytes(self):
        return self.size * self.itemsize

    # methods

    def __getitem__(self, item):

        # normalize selection
        selection = normalize_array_selection(item, self._shape)

        # determine output array shape
        out_shape = tuple(stop - start for start, stop in selection)

        # setup output array
        out = np.empty(out_shape, dtype=self._dtype)

        # determine indices of chunks overlapping the selection
        chunk_range = get_chunk_range(selection, self._chunks)

        # iterate over chunks in range
        for cidx in itertools.product(*chunk_range):

            # determine chunk offset
            offset = [i * c for i, c in zip(cidx, self._chunks)]

            # determine region within output array
            out_selection = tuple(
                slice(max(0, o - start), min(o + c - start, stop - start))
                for (start, stop), o, c, in zip(selection, offset, self._chunks)
            )

            # determine region within chunk
            chunk_selection = tuple(
                slice(max(0, start - o), min(c, stop - o))
                for (start, stop), o, c in zip(selection, offset, self._chunks)
            )

            # obtain the destination array as a view of the output array
            dest = out[out_selection]

            # load chunk selection into output array
            self._chunk_getitem(cidx, chunk_selection, dest)

        return out

    def __array__(self):
        return self[:]

    def __setitem__(self, key, value):

        # normalize selection
        selection = normalize_array_selection(key, self._shape)

        # determine indices of chunks overlapping the selection
        chunk_range = get_chunk_range(selection, self._chunks)

        # iterate over chunks in range
        for cidx in itertools.product(*chunk_range):

            # determine chunk offset
            offset = [i * c for i, c in zip(cidx, self._chunks)]

            # determine required index range within chunk
            chunk_selection = tuple(
                slice(max(0, start - o), min(c, stop - o))
                for (start, stop), o, c in zip(selection, offset, self._chunks)
            )

            if np.isscalar(value):

                # put data
                self._chunk_setitem(cidx, chunk_selection, value)

            else:
                # assume value is array-like

                # determine index within value
                value_selection = tuple(
                    slice(max(0, o - start), min(o + c - start, stop - start))
                    for (start, stop), o, c, in zip(selection, offset, self._chunks)
                )

                # put data
                self._chunk_setitem(cidx, chunk_selection, value[value_selection])

    def _chunk_getitem(self, cidx, item, dest):
        """Obtain part or whole of a chunk.

        Parameters
        ----------
        cidx : tuple of ints
            Indices of the chunk.
        item : tuple of slices
            Location of region within the chunk.
        dest : ndarray
            Numpy array to store result in.

        """

        # override this in sub-classes, e.g., if need to use a lock

        # obtain compressed data for chunk
        cdata = self._store.data[cidx]

        if is_total_slice(item, self._chunks) and dest.flags.c_contiguous:

            # optimisation: we want the whole chunk, and the destination is
            # C contiguous, so we can decompress directly from the chunk
            # into the destination array
            decompress(cdata, dest)

        else:

            # decompress chunk
            chunk = np.empty(self._chunks, dtype=self._dtype)
            decompress(cdata, chunk)

            # set data in output array
            # (split into two lines for profiling)
            tmp = chunk[item]
            dest[:] = tmp

    def _chunk_setitem(self, cidx, key, value):
        """Replace part or whole of a chunk.

        Parameters
        ----------
        cidx : tuple of ints
            Indices of the chunk.
        key : tuple of slices
            Location of region within the chunk.
        value : scalar or ndarray
            Value to set.

        """

        # override this in sub-classes, e.g., if need to use a lock

        if is_total_slice(key, self._chunks):

            # optimisation: we are completely replacing the chunk, so no need
            # to access the existing chunk data

            if np.isscalar(value):

                # setup array filled with value
                chunk = np.empty(self._chunks, dtype=self._dtype)
                chunk.fill(value)

            else:

                # ensure array is C contiguous
                chunk = np.ascontiguousarray(value, dtype=self._dtype)

        else:
            # partially replace the contents of this chunk

            # obtain compressed data for chunk
            cdata = self._store.data[cidx]

            # decompress
            chunk = np.empty(self._chunks, dtype=self._dtype)
            decompress(cdata, chunk)

            # modify
            chunk[key] = value

        # compress
        cdata = compress(chunk, self._cname, self._clevel, self._shuffle)

        # store
        self._store.data[cidx] = cdata

    def __repr__(self):
        # TODO
        pass

    def __str__(self):
        # TODO
        pass

    def resize(self, *args):
        # TODO
        pass

    def append(self, data, axis=0):
        # TODO
        pass


class SynchronizedArray(Array):

    def __init__(self, store, synchronizer):
        super(SynchronizedArray, self).__init__(store)
        self._synchronizer = synchronizer

    def _chunk_setitem(self, cidx, key, value):
        with self._synchronizer.lock_chunk(cidx):
            super(SynchronizedArray, self)._chunk_setitem(cidx, key, value)

    # TODO synchronize anything else?
