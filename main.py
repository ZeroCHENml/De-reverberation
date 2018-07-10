import pdb
import sys

import numpy as np
import cupy as cp
import scipy as sc
import scipy.io as scio

# import matplotlib.pyplot as plt

import os
from glob import glob

from pre_processing import PreProcessor as Pre
import show_IV_image as showIV
from train_nn import NNTrainer

if __name__ == '__main__':
    DIR_WAVFILE = './speech/data/lisa/data/timit/raw/TIMIT/TRAIN/'
    DIR = './IV'
    DIR_TRAIN = './IV/TRAIN/'
    DIR_TEST = './IV/TEST/'
    FORM = '%04d_%02d'
    X_POSTFIX = '_room.npy'
    Y_POSTFIX = '_free.npy'
    FORM_FREE = FORM+Y_POSTFIX
    FORM_ROOM = FORM+X_POSTFIX
    ID = '*_converted.wav'

    for arg in sys.argv[1:]:
        if arg == 'pre_processing':
            #RIR Data
            RIR = scio.loadmat('./1_MATLABCode/RIR.mat',
                                variable_names = 'RIR')['RIR']
            RIR = RIR.transpose((2, 0, 1)) #72 x 32 x 48k
            RIR = cp.array(RIR)

            #SFT Data
            sph_mat = scio.loadmat('./1_MATLABCode/sph_data.mat',
                    variable_names=['bEQspec','Yenc','Ys','Wnv','Wpv','Vv'])
            bEQspec = cp.array(sph_mat['bEQspec']).T
            Yenc = cp.array(sph_mat['Yenc']).T

            Ys_original = sph_mat['Ys'].reshape(-1)
            Ys_np = np.zeros((Ys_original.size,Ys_original[0].size),
                             dtype=complex)
            for ii in range(Ys_original.size):
                Ys_np[ii] = Ys_original[ii].reshape(-1)
            Ys = cp.array(Ys_np)
            del Ys_original

            Wnv = cp.array(sph_mat['Wnv'], dtype=complex).reshape(-1)
            Wpv = cp.array(sph_mat['Wpv'], dtype=complex).reshape(-1)
            Vv = cp.array(sph_mat['Vv'], dtype=complex).reshape(-1)

            del sph_mat

            N_START = len(glob(
                os.path.join(DIR_TRAIN, '*_%02d_room.npy'%(RIR.shape[0]-1))
            ))+1

            p = Pre(RIR, bEQspec, Yenc, Ys, Wnv, Wpv, Vv)
            p.process(DIR_WAVFILE, ID, N_START, DIR_TRAIN, FORM_FREE, FORM_ROOM)

        else:
            metadata = np.load('metadata.npy').item()

            Fs = metadata['Fs']
            N_fft = metadata['N_fft']
            L_frame = metadata['L_frame']
            L_hop = metadata['L_hop']
            N_wavfile = metadata['N_wavfile']
            N_loc = metadata['N_LOC']

            del metadata

            if arg.startswith('show_IV_image'):
                IDX_WAV = 1
                IDX_LOC = 0
                arg_sp = arg.split()
                try:
                    IDX_WAV = int(arg_sp[1])
                    IDX_LOC = int(arg_sp[2])
                except IndexError:
                    pass

                FNAME_FREE = os.path.join(DIR_TRAIN,
                                          FORM_FREE%(IDX_WAV,IDX_LOC))
                FNAME_ROOM = os.path.join(DIR_TRAIN,
                                          FORM_ROOM%(IDX_WAV,IDX_LOC))

                showIV.show(FNAME_FREE, FNAME_ROOM, ylim=[0, Fs/2])
            elif arg.startswith('train_nn'):
                trainer = NNTrainer(Fs, N_fft, L_frame, L_hop,
                                    DIR, DIR_TRAIN, DIR_TEST,
                                    FORM, X_POSTFIX, Y_POSTFIX)
                trainer.train()

            # elif arg.startswith('histogram'):
            #     IV_free = np.load(FNAME_FREE)
            #     IV_room = np.load(FNAME_ROOM)
            #     bins = 200
            #
            #     plt.figure()
            #     plt.subplot(2,2,1)
            #     plt.hist(IV_free[:,:,:3].reshape(-1), bins=bins)
            #     plt.xlim(IV_free[:,:,:3].min(), IV_free[:,:,:3].max())
            #     plt.title('Histogram for RGB (Free-space)')
            #     plt.subplot(2,2,2)
            #     plt.hist(IV_free[:,:,3].reshape(-1), bins=bins)
            #     plt.xlim(IV_free[:,:,3].min(), IV_free[:,:,3].max())
            #     plt.title('Histogram for alpha (Free-space)')
            #     plt.subplot(2,2,3)
            #     plt.hist(IV_room[:,:,:3].reshape(-1), bins=bins)
            #     plt.xlim(IV_room[:,:,:3].min(), IV_room[:,:,:3].max())
            #     plt.title('Histogram for RGB (Room)')
            #     plt.subplot(2,2,4)
            #     plt.hist(IV_room[:,:,3].reshape(-1), bins=bins)
            #     plt.xlim(IV_room[:,:,3].min(), IV_room[:,:,3].max())
            #     plt.title('Histogram for alpha (Room))')
            #     plt.show()
