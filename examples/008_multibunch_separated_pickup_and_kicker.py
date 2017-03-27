# This file can be run by using the following command:
#$ mpirun -np 4 python 008_multibunch_separated_pickup_and_kicker.py

"""
    This is a simple example for a multi bunch MPI feedback. It is based on the ideal bunch
    feedback presented in the file '002_separated_pickup_and_kicker.ipynb'. The only difference
    is that multiple bunches are simulated in parallel in this example.
"""


from __future__ import division

import sys, os
BIN = os.path.expanduser("../../")
sys.path.append(BIN)

import time
import numpy as np
import seaborn as sns
from mpi4py import MPI
import matplotlib.pyplot as plt
from scipy.constants import c, e, m_p, pi

from PyHEADTAIL.particles.slicing import UniformBinSlicer
from PyHEADTAIL_feedback.feedback import Kicker, PickUp
from PyHEADTAIL_feedback.processors.multiplication import ChargeWeighter
from PyHEADTAIL_feedback.processors.linear_transform import Averager
from PyHEADTAIL_feedback.processors.misc import Bypass
from PyHEADTAIL_feedback.processors.register import Register

plt.switch_backend('TkAgg')
sns.set_context('talk', font_scale=1.3)
sns.set_style('darkgrid', {
    'axes.edgecolor': 'black',
    'axes.linewidth': 2,
    'lines.markeredgewidth': 1})



def pick_signals(processor, source = 'input'):
    """
    A function which helps to visualize the signals passing the signal processors.
    :param processor: a reference to the signal processor
    :param source: source of the signal, i.e, 'input' or 'output' signal of the processor
    :return: (t, z, bins, signal), where 't' and 'z' are time or position values for the signal values (which can be used
        as x values for plotting), 'bins' are data for visualizing sampling and 'signal' is the actual signal.
    """
    print processor
    if source == 'input':
        bin_edges = processor.input_parameters['bin_edges']
        raw_signal = processor.input_signal
    elif source == 'output':
        bin_edges = processor.output_parameters['bin_edges']
        raw_signal = processor.output_signal
    else:
        raise ValueError('Unknown value for the data source')

    z = np.zeros(len(raw_signal)*4)
    bins = np.zeros(len(raw_signal)*4)
    signal = np.zeros(len(raw_signal)*4)
    value = 1.

    for i, edges in enumerate(bin_edges):
        z[4*i] = edges[0]
        z[4*i+1] = edges[0]
        z[4*i+2] = edges[1]
        z[4*i+3] = edges[1]
        bins[4*i] = 0.
        bins[4*i+1] = value
        bins[4*i+2] = value
        bins[4*i+3] = 0.
        signal[4*i] = 0.
        signal[4*i+1] = raw_signal[i]
        signal[4*i+2] = raw_signal[i]
        signal[4*i+3] = 0.
        value *= -1

    t = z/c

    return (t, z, bins, signal)


def kicker(bunch):
    """
    A function which sets initial kicks for the bunches. The function is passed to the bunch generator
    in the machine object.
    """
    bunch.x *= 0
    bunch.xp *= 0
    bunch.y *= 0
    bunch.yp *= 0
    bunch.x[:] += 2e-2 * np.sin(2.*pi*np.mean(bunch.z)/1000.)


comm = MPI.COMM_WORLD
size = comm.Get_size()
rank = comm.Get_rank()

# SIMULATION, BEAM AND MACHNINE PARAMETERS
# ========================================
n_turns = 100
n_segments = 1
n_macroparticles = 40000

from test_tools import MultibunchMachine
machine = MultibunchMachine(n_segments=n_segments)

intensity = 2.3e11
epsn_x = 2.e-6
epsn_y = 2.e-6
sigma_z = 0.081


# FILLING SCHEME
# ==============
# Bunches are created by creating a list of numbers representing the RF buckets to be filled.

n_bunches = 13
filling_scheme = [401 + 20*i for i in range(n_bunches)]

# Machine returns a super bunch, which contains particles from all of the bunches
# and can be split into separate bunches
bunches = machine.generate_6D_Gaussian_bunch_matched(
    n_macroparticles, intensity, epsn_x, epsn_y, sigma_z=sigma_z,
    filling_scheme=filling_scheme, kicker=kicker)


# CREATE BEAM SLICERS
# ===================
slicer = UniformBinSlicer(50, n_sigma_z=3)


# FEEDBACK MAP
# ==============
# Actual code for the feedback. It is exactly same as used in the file
# '002_separated_pickup_and_kicker.ipynb' expect that 'mpi' flag is set into 'True'.
#
# The flags 'store_signal' of the signal processors are set into 'True'
#  in order to visualize signal processing after the simulation,

pickup_beta_x = machine.beta_x_inj
pickup_beta_y = machine.beta_y_inj

kicker_beta_x = machine.beta_x_inj
kicker_beta_y = machine.beta_y_inj

pickup_location_x = 1.*2.*pi/float(n_segments)*machine.Q_x
pickup_location_y = 1.*2.*pi/float(n_segments)*machine.Q_y

kicker_location_x = 2.*2.*pi/float(n_segments)*machine.Q_x
kicker_location_y = 2.*2.*pi/float(n_segments)*machine.Q_y

delay = 1
n_values = 3

processors_pickup_x = [
    ChargeWeighter(normalization = 'segment_average',store_signal  = True),
    Averager(store_signal  = True),
    Register(n_values, machine.Q_x, delay,store_signal  = True)
]
processors_pickup_y = [
    ChargeWeighter(normalization = 'segment_average',store_signal  = True),
    Averager(store_signal  = True),
    Register(n_values, machine.Q_y, delay,store_signal  = True)
]

pickup_map = PickUp(slicer,processors_pickup_x,processors_pickup_y,
                    pickup_location_x, pickup_beta_x, pickup_location_y, pickup_beta_y, mpi = True)

processors_kicker_x = [Bypass(store_signal  = True)]
processors_kicker_y = [Bypass(store_signal  = True)]

registers_x = [processors_pickup_x[-1]]
registers_y = [processors_pickup_y[-1]]

gain = 0.1

kicker_map = Kicker(gain, slicer,
                    processors_kicker_x, processors_kicker_y, registers_x, registers_y,
                    kicker_location_x, kicker_beta_x, kicker_location_y, kicker_beta_y, mpi = True)

# The kicker and the pickup are placed into the correct slots of the one turn map

new_one_turn_map = []
for i, m in enumerate(machine.one_turn_map):

    if i == 1:
        new_one_turn_map.append(pickup_map)

    if i == 2:
        new_one_turn_map.append(kicker_map)

    new_one_turn_map.append(m)

machine.one_turn_map = new_one_turn_map

# TRACKING LOOP
# =============
s_cnt = 0
monitorswitch = False
if rank == 0:
    print '\n--> Begin tracking...\n'

print 'Tracking'
for i in range(n_turns):

    if rank == 0:
        t0 = time.clock()
    machine.track(bunches)

    if rank == 0:
        t1 = time.clock()
        print('Turn {:d}, {:g} ms, {:s}'.format(i, (t1-t0)*1e3, time.strftime(
            "%d/%m/%Y %H:%M:%S", time.localtime())))

if rank == 0:
    # On the first processor, the script plots signals passed each signal processor from
    # the last simulated turn of the simulation

    fig, (ax1, ax2) = plt.subplots(2, figsize=(14, 14), sharex=False)
    fig.suptitle('Pickup processors', fontsize=20)

    for i, processor in enumerate(processors_pickup_x):
        t, z, bins, signal = pick_signals(processor,'output')
        ax1.plot(z, bins*(0.9**i), label =  processor.label)
        ax2.plot(z, signal, label =  processor.label)

    # The first plot represents sampling in the each signal processor. The magnitudes of the curves do not represent
    # anything, but the change of the polarity represents a transition from one bin to another.
    ax1.set_ylim([-1.1, 1.1])
    ax1.set_xlabel('Z position [m]')
    ax1.set_ylabel('Bin set')
    ax1.legend(loc='upper left')

    # Actual signals
    ax2.set_xlabel('Z position [m]')
    ax2.set_ylabel('Signal')
    ax2.legend(loc='upper left')

    fig, (ax3, ax4) = plt.subplots(2, figsize=(14, 14), sharex=False)
    fig.suptitle('Kicker processors', fontsize=20)

    for i, processor in enumerate(processors_kicker_x):
        t, z, bins, signal = pick_signals(processor,'output')
        ax3.plot(z, bins*(0.9**i), label =  processor.label)
        ax4.plot(z, signal, label =  processor.label)

    # The first plot represents sampling in the each signal processor. The magnitudes of the curves do not represent
    # anything, but the change of the polarity represents a transition from one bin to another.
    ax3.set_ylim([-1.1, 1.1])
    ax3.set_xlabel('Z position [m]')
    ax3.set_ylabel('Bin set')
    ax3.legend(loc='upper left')

    # Actual signals
    ax4.set_xlabel('Z position [m]')
    ax4.set_ylabel('Signal')
    ax4.legend(loc='upper left')

    plt.show()