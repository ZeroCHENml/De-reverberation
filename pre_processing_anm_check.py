import pdb  # noqa: F401

import numpy as np
import cupy as cp
import scipy.signal as scsig

import os
from os import path
import time
from glob import glob
import deepdish as dd

from typing import Tuple, NamedTuple, TypeVar, List

import soundfile as sf

import multiprocessing as mp
import logging  # noqa: F401

N_CUDA_DEV = 4
NDArray = TypeVar('NDArray', np.ndarray, cp.ndarray)


def search_all_files(DIR_WAVFILE: str, ID: str) -> List[str]:
    result = []
    for folder, _, _ in os.walk(DIR_WAVFILE):
        files = glob(path.join(folder, ID))
        if not files:
            continue
        result += files

    return result


class SFTData(NamedTuple):
    """
    Constant Matrices/Vectors for Spherical Fourier Analysis
    """
    bEQspec: NDArray
    Yenc: NDArray
    Wnv: NDArray
    Wpv: NDArray
    Vv: NDArray

    def get_triags(self) -> Tuple:
        return (self.Wnv, self.Wpv, self.Vv)


class PreProcessor:
    def __init__(self, RIRs: np.ndarray, Ys: np.ndarray, sftdata: SFTData,
                 L_WIN_MS=20., RIRs_0: np.ndarray=None):
        # Bug Fix
        np.fft.restore_all()
        # From Parameters
        self.RIRs = RIRs
        self.N_LOC, self.N_MIC, self.L_RIR = RIRs.shape
        self.Ys = Ys
        self.RIRs_0 = RIRs_0
        self.sftdata = sftdata

        self.L_WIN_MS = L_WIN_MS

        # Determined during process
        self.DIR_IV = ''
        self.all_files = []

        # Common for all wave file
        self.Fs = 0
        self.N_wavfile = 0
        self.N_fft = 0
        self.N_freq = 0
        self.L_frame = 0
        self.L_hop = 0
        self.win = None

    def process(self, DIR_WAVFILE: str, ID: str, idx_start: int,
                DIR_IV: str, FORM: str, N_CORES=mp.cpu_count()//4):
        if not path.exists(DIR_IV):
            os.makedirs(DIR_IV)
        self.DIR_IV = DIR_IV

        if self.N_LOC < mp.cpu_count():
            N_CORES = self.N_LOC
        n_loc_per_core = int(np.ceil(self.N_LOC//N_CORES))

        max_n_pool = 1
        while max_n_pool*int(np.ceil(n_loc_per_core*N_CORES/N_CUDA_DEV)) < 30:
            max_n_pool += 1
        max_n_pool -= 1

        print(f'Start processing from the {idx_start}-th wave file')

        # Search all wave files
        # self.all_files = search_all_files(DIR_WAVFILE, ID)
        self.Fs = 16000
        data = np.random.normal(size=(16000*10))
        self.L_frame = int(self.Fs*self.L_WIN_MS//1000)
        self.N_fft = self.L_frame
        if self.N_fft % 2 == 0:
            self.N_freq = self.N_fft//2 + 1
        else:
            self.N_freq = self.N_fft//2
        self.L_hop = self.L_frame//2

        self.win = scsig.hamming(self.L_frame, sym=False)

        pdb.set_trace()
        # Main Process
        for i_proc in range(N_CORES):
            if (i_proc + 1) * n_loc_per_core <= self.N_LOC:
                range_loc = range(i_proc * n_loc_per_core,
                                  (i_proc+1) * n_loc_per_core)
            elif i_proc * n_loc_per_core < self.N_LOC:
                range_loc = range(i_proc * n_loc_per_core, self.N_LOC)
            else:
                break
            self.save_IV(i_proc % N_CUDA_DEV,
                         data,
                         range_loc,
                         FORM, self.N_wavfile+1)

    def save_IV(self, i_dev: int, data: NDArray, range_loc: iter,
                FORM: str, *args):
        """
        Save IV files.

        i_dev: GPU Device No.
        range_loc: RIR Index Range(S/M Location Index Range)
        FORM: format of filename
        args: format string arguments

        return: None
        """
        # CUDA Ready
        cp.cuda.Device(i_dev).use()
        data = cp.array(data)
        win = cp.array(self.win)
        Ys = cp.array(self.Ys)
        sftdata = SFTData(*[cp.array(item) for item in self.sftdata])

        N_frame_free = data.shape[0]//self.L_hop - 1
        N_frame_room = (data.shape[0]+self.L_RIR-1)//self.L_hop - 1

        for i_loc in range_loc:
            # RIR Filtering
            data_0 \
                = cp.array(scsig.fftconvolve(cp.asnumpy(data.reshape(1, -1)),
                                             self.RIRs_0[i_loc]))

            # using 0-th Order RIR
            iv_0 = cp.zeros((self.N_freq, N_frame_room, 16), dtype=complex)
            for i_frame in range(N_frame_room):
                interval = i_frame*self.L_hop + np.arange(self.L_frame)
                fft = cp.fft.fft(data_0[:, interval]*win, n=self.N_fft)
                anm = (sftdata.Yenc @ fft) * sftdata.bEQspec

                iv_0[:, i_frame, :] = anm[:, :self.N_freq].T

            # Free-field Intensity Vector Image
            iv_free = cp.zeros((self.N_freq, N_frame_free, 16), dtype=complex)
            for i_frame in range(N_frame_free):
                interval = i_frame*self.L_hop + np.arange(self.L_frame)
                fft = cp.fft.fft(data[interval]*win, n=self.N_fft)
                anm = cp.outer(Ys[i_loc].conj(), fft)

                iv_free[:, i_frame, :] = anm[:, :self.N_freq].T

            # Save
            dict_to_save = {'IV_free': cp.asnumpy(iv_free),
                            # 'IV_room': cp.asnumpy(iv_room),
                            'IV_0': cp.asnumpy(iv_0),
                            # 'data': cp.asnumpy(data),
                            # 'norm_factor_free': norm_factor_free,
                            # 'norm_factor_room': norm_factor_room,
                            }
            FNAME = FORM % (*args, i_loc)
            dd.io.save(path.join(self.DIR_IV, FNAME),
                       dict_to_save,
                       compression=None)

            print(FORM % (*args, i_loc))

    def __str__(self):
        return ('Wave Files Processed/Total: '
                f'{self.N_wavfile}/{len(self.all_files)}\n'
                f'Sample Rate: {self.Fs}\n'
                f'Number of source location: {self.N_LOC}\n'
                )

    def print_save_info(self):
        """
        Print __str__ and save metadata.
        """
        print(self)

        metadata = {'N_wavfile': self.N_wavfile,
                    'Fs': self.Fs,
                    # 'N_fft': self.N_fft,
                    'N_freq': self.N_freq,
                    'L_frame': self.L_frame,
                    'L_hop': self.L_hop,
                    'N_LOC': self.N_LOC,
                    'path_wavfiles': self.all_files,
                    }

        dd.io.save(path.join(self.DIR_IV, 'metadata.h5'), metadata)

    @staticmethod
    def seltriag(Ain: NDArray, nrord: int, shft: Tuple[int, int]) -> NDArray:
        xp = cp.get_array_module(Ain)
        N_freq = 1 if Ain.ndim == 1 else Ain.shape[1]
        N = int(np.ceil(np.sqrt(Ain.shape[0]))-1)
        idx = 0
        len_new = (N-nrord+1)**2

        Aout = xp.zeros((len_new, N_freq), dtype=Ain.dtype)
        for ii in range(N-nrord+1):
            for jj in range(-ii, ii+1):
                n = shft[0] + ii
                m = shft[1] + jj
                idx_from = m + n*(n+1)
                if -n <= m and m <= n and 0 <= n and n <= N \
                        and idx_from < Ain.shape[0]:
                    Aout[idx] = Ain[idx_from]
                idx += 1
        return Aout

    @classmethod
    def calc_intensity(cls, Asv: NDArray,
                       Wnv: NDArray, Wpv: NDArray, Vv: NDArray) -> NDArray:
        """
        Asv(anm) -> IV
        """
        xp = cp.get_array_module(Asv)

        aug1 = cls.seltriag(Asv, 1, (0, 0))
        aug2 = cls.seltriag(Wpv, 1, (1, -1))*cls.seltriag(Asv, 1, (1, -1)) \
            - cls.seltriag(Wnv, 1, (0, 0))*cls.seltriag(Asv, 1, (-1, -1))
        aug3 = cls.seltriag(Wpv, 1, (0, 0))*cls.seltriag(Asv, 1, (-1, 1)) \
            - cls.seltriag(Wnv, 1, (1, 1))*cls.seltriag(Asv, 1, (1, 1))
        aug4 = cls.seltriag(Vv, 1, (0, 0))*cls.seltriag(Asv, 1, (-1, 0)) \
            + cls.seltriag(Vv, 1, (1, 0))*cls.seltriag(Asv, 1, (1, 0))

        dx = (aug1.conj()*(aug2+aug3)/2).sum(axis=0)
        dy = (aug1.conj()*(aug2-aug3)/2j).sum(axis=0)
        dz = (aug1.conj()*aug4).sum(axis=0)

        return 0.5*xp.real(xp.stack((dx, dy, dz), axis=1))


if __name__ == '__main__':
    pass
