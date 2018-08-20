"""
Module for computing frequency bands from raw EEG data. All of the interesting
math here comes from https://github.com/NeuroTechX/bci-workshop
"""

import numpy as np
from .models import Sample
from scipy.signal import butter, lfilter, lfilter_zi
import itertools

NOTCH_B, NOTCH_A = butter(4, np.array([55, 65]) / (256 / 2), btype='bandstop')
CHANNEL_INDICES = [0, 1, 2, 3]
SAMPLING_FREQUENCY = 256

def _update_buffer(data_buffer, new_data, notch=False, filter_state=None):
    """
    Concatenates "new_data" into "data_buffer", and returns an array with
    the same size as "data_buffer"
    """
    if new_data.ndim == 1:
        new_data = new_data.reshape(-1, data_buffer.shape[1])

    if notch:
        if filter_state is None:
            filter_state = np.tile(lfilter_zi(NOTCH_B, NOTCH_A),
                                   (data_buffer.shape[1], 1)).T
        new_data, filter_state = lfilter(NOTCH_B, NOTCH_A, new_data, axis=0,
                                         zi=filter_state)

    new_buffer = np.concatenate((data_buffer, new_data), axis=0)
    new_buffer = new_buffer[new_data.shape[0]:, :]

    return new_buffer, filter_state

def _compute_feature_vector(eeg_data):
    """
    Extract the features from the EEG.

    Args:
        eeg_data (numpy.ndarray): array of dimension [number of samples,
                number of channels]

    Returns:
        (numpy.ndarray): feature matrix of shape [number of feature points,
            number of different features]
    """
    
    # Compute the PSD
    win_sample_length, _ = eeg_data.shape

    # Apply Hamming window
    w = np.hamming(win_sample_length)
    data_win_centered = eeg_data - np.mean(eeg_data, axis=0)  # Remove offset
    data_win_centered_ham = (data_win_centered.T * w).T

    nfft = _nextpow2(win_sample_length)
    y = np.fft.fft(data_win_centered_ham, n=nfft, axis=0) / win_sample_length
    psd = 2 * np.abs(y[0 : int(nfft / 2), :])
    f = SAMPLING_FREQUENCY / 2 * np.linspace(0, 1, int(nfft / 2))

    # SPECTRAL FEATURES
    # Average of band powers
    # Delta <4
    ind_delta, = np.where(f < 4)
    mean_delta = np.mean(psd[ind_delta, :], axis=0)

    # Theta 4-8
    ind_theta, = np.where((f >= 4) & (f <= 8))
    mean_theta = np.mean(psd[ind_theta, :], axis=0)

    # Alpha 8-12
    ind_alpha, = np.where((f >= 8) & (f <= 12))
    mean_alpha = np.mean(psd[ind_alpha, :], axis=0)

    # Beta 12-30
    ind_beta, = np.where((f >= 12) & (f < 30))
    mean_beta = np.mean(psd[ind_beta, :], axis=0)

    feature_vector = np.concatenate((mean_delta, mean_theta, mean_alpha,
                                     mean_beta), axis=0)

    feature_vector = np.log10(feature_vector)

    return feature_vector

def _nextpow2(i):
    """
    Find the next power of 2 for number i
    """
    n = 1
    while n < i:
        n *= 2
    return n

def get_waves(raw_data, chunk_size=SAMPLING_FREQUENCY):
    last_timestamp = None
    eeg_buffer = np.zeros((int(SAMPLING_FREQUENCY), len(CHANNEL_INDICES)))
    filter_state = None

    while True:
        samples = list(itertools.islice(raw_data, chunk_size))

        if not samples:
            break

        # Remove any samples we've already processed
        if last_timestamp is not None:
            samples = [s for s in samples if s.timestamp > last_timestamp]

        if not samples:
            continue

        timestamps = np.array([s.timestamp for s in samples])
        ch_data = np.array([s.data[:4] for s in samples])
        eeg_buffer, filter_state = _update_buffer(eeg_buffer, ch_data, notch=True, filter_state=filter_state)

        last_timestamp = samples[-1].timestamp

        # calculate feature vector, then split it up to its respective bands
        feat_vector = _compute_feature_vector(eeg_buffer)
        delta_vector, theta_vector, alpha_vector, beta_vector = np.split(feat_vector, 4)

        yield (
            Sample(last_timestamp, delta_vector),
            Sample(last_timestamp, theta_vector),
            Sample(last_timestamp, alpha_vector),
            Sample(last_timestamp, beta_vector),
        )
