"""
This script implements reinforcement learning with faults on a fuel tank system
represented by a netlist (models/fuel_tanks.netlist). There are 6 tanks. 4 of
the tanks are primary tanks and have a outputs to engines. The remaining 2 are
auxiliary tanks which feed into the primary tanks. Each tank is represented
by a capacitor. Resistors are used to simulate internal resistances and
switches. The system rewards fuel tanks balanced on each side and penalizes
imbalance. Faults in the system are leak(s) in fuel tanks.

Fuel tanks are arranged physically as:

    T1  T2  TLAux   |   TRAux   T3  T4

You can use LTSpice (or similar applications) to view the graphical circuit
representation of the system in: models/fuel_tanks.asc

Usage:

> python tanks.py --help

Default model and learning parameters can be changed below. Some of them
can be tuned from the command-line.
"""

import numpy as np
import flask
from argparse import ArgumentParser
from qlearn import Netlist
from qlearn import FlagGenerator
from qlearn import Simulator
from qlearn import SLearner
from qlearn import utils

# Default model configuration parameters
NETLIST_FILE = 'models/fuel_tanks.netlist'
ON_RESISTANCE = 1e1
OFF_RESISTANCE = 1e6
INTERNAL_RESISTANCE = 1e3
CAPACITANCE = 1e-3
MAX_SIM_TSTEP = 1e-1
DELTA_T = 1e-1
NUM_TANKS = 6
NUM_LEVELS = 5

# Default learning configuration parameters
GOAL_THRESH = 0.2
COVERAGE = 0.2
LRATE = 1e-2
DISCOUNT = 1
EXPLORATION = 0.5
POLICY = SLearner.UNIFORM
DEPTH = 5
STEPS = 1
SEED = None
INTERVAL = DEPTH

# Set up command-line configuration
args = ArgumentParser()
args.add_argument('-n', '--num_levels', metavar='N', type=int,
                  help="Number of levels per tank", default=NUM_LEVELS)
args.add_argument('-c', '--coverage', metavar='C', type=float,
                  help="Fraction of states to cover in learning", default=COVERAGE)
args.add_argument('-r', '--rate', metavar='R', type=float,
                  help="Learning rate (0, 1]", default=LRATE)
args.add_argument('-d', '--discount', metavar='D', type=float,
                  help="Discount factor (0, 1]", default=DISCOUNT)
args.add_argument('-e', '--explore', metavar='E', type=float,
                  help="Exploration while recommending actions [0, 1]", default=EXPLORATION)
args.add_argument('-s', '--steps', metavar='S', type=int,
                  help="Number of steps to look ahead during learning", default=STEPS)
args.add_argument('-m', '--maxlimit', metavar='M', type=int,
                  help="Number of steps at most in each learning episode", default=DEPTH)
args.add_argument('-t', '--interval', metavar='T', type=int,
                  help="Number of steps between re-learning policy", default=INTERVAL)
args.add_argument('-p', '--policy', metavar='P', choices=['uniform', 'softmax', 'greedy'],
                  help="The action selection policy", default=POLICY)
args.add_argument('-l', '--load', metavar='F', type=str,
                  help="File to load learned policy from", default='')
args.add_argument('-f', '--file', metavar='F', type=str,
                  help="File to save learned policy to", default='')
args.add_argument('--seed', metavar='SEED', type=int,
                  help="Random number seed", default=SEED)
ARGS = args.parse_args()

# Specify dimension and resolution of state and action vectors
# A state vector is a NUM_TANKS+1 vector where the last element is the open valve
# and the first NUM_TANKS elements are potentials in tanks
STATES = FlagGenerator(*[ARGS.num_levels] * NUM_TANKS, 14)
# An action vector is a single element vector signalling which of the 14 valves
# is active. Same as the last element in state vector
ACTIONS = FlagGenerator(14)


# Instantiate netlist representing the fuel tank system
NET = Netlist('Tanks', path=NETLIST_FILE)
INITIAL = NET.directives['ic'][0]


# Get list of resistors to be used as switches - ignoring internal resistances
RESISTORS = [r for r in NET.elements_like('r') if not r.name.startswith('ri')]
for res in RESISTORS:
    res.value = OFF_RESISTANCE
# Set internal resistances
for rint in NET.elements_like('ri'):
    rint.value = INTERNAL_RESISTANCE
# Get list of capacitors representing fuel tanks and set values
CAPACITORS = NET.elements_like('c')     # [c1, c2, c3, c4, cl, cr]
for cap in CAPACITORS:
    cap.value = CAPACITANCE


# Define a state mux for the simulator which converts state and action vectors
# into changes in the netlist
def state_mux(svec, avec, netlist):
    for i in range(NUM_TANKS):
        INITIAL.param('v(' + str(CAPACITORS[i].nodes[0]) + ')', svec[i])
    for resistor in RESISTORS:
        resistor.value = OFF_RESISTANCE
    RESISTORS[int(avec[0])].value = ON_RESISTANCE
    return NET


# Define state demux for the simulator which converts simulation results into
# a state vector
def state_demux(psvec, pavec, netlist, result):
    svec = np.zeros(NUM_TANKS+1)
    svec[-1] = pavec[0]
    for i in range(NUM_TANKS):
        svec[i] = result['v(' + str(CAPACITORS[i].nodes[0]) + ')']
    return svec


# The reward function returns a measure of the desirability of a state,
# in this case the moment about the central axis
def reward(svec, avec, nsvec):
    moment = 3 * (nsvec[0] - nsvec[3]) + \
             2 * (nsvec[1] - nsvec[2]) + \
             1 * (nsvec[4] - nsvec[5])
    return -abs(moment) # reward is always negative, max=0


# Get minimum possible reward, to use as a threshold for measuring goal state
MIN_REWARD = abs(reward(None, None, np.ones(NUM_TANKS) * NUM_LEVELS))


# Returns Trus if a state is considered a terminal/goal state
def goal(svec):
    return abs(reward(None, None, svec)) < GOAL_THRESH * MIN_REWARD


# Returns the gradient of the policy function w.r.t weights: a vector of length
# FUNCDIM (see below)
def dfunc(svec, avec, weights):
    valves = np.zeros(14)
    valves[int(avec[0])] = 1
    return np.concatenate((svec[:-1], valves))


# Returns the value of a state/action given weights. The policy function.
# Used to compute the optimal action from each state when exploiting a policy.
def func(svec, avec, weights):
    return np.dot(dfunc(svec, avec, weights), weights)


# Number of weights to learn in functional approximation, in this case:
# 1 weight for each tank and 1 weight for each valve
FUNCDIM = NUM_TANKS + 14


# Define a fault function. Calling it with an argument introduces a fault in the
# system defined by NET.
def create_fault(fault_num):
    if fault_num < 0:
        faulty_resistors = NET.elements_like('rf')
        for resistor in faulty_resistors:
            NET.remove(resistor)


# Create a simulator to be used by SLearner
SIM = Simulator(env=NET, timestep=MAX_SIM_TSTEP, state_mux=state_mux,
                state_demux=state_demux)


# Create the SLearner instance
LEARNER = SLearner(reward=reward, simulator=SIM, stateconverter=STATES,
                   actionconverter=ACTIONS, goal=goal, func=func, funcdim=FUNCDIM,
                   dfunc=dfunc, lrate=ARGS.rate, discount=ARGS.discount,
                   exploration=ARGS.explore, policy=ARGS.policy, depth=ARGS.maxlimit,
                   steps=ARGS.steps, seed=ARGS.seed)


# Print paramters
for key, value in vars(ARGS).items():
    print('%12s: %-12s' % (key, value))
# Loading weights or learning new policy
if ARGS.load == '':
    input('\nPress Enter to begin learning.')
    print('Learning episodes: %5d out of %d states' %
          (int(ARGS.coverage * STATES.num_states), STATES.num_states))
    LEARNER.learn(coverage=ARGS.coverage, verbose=True)
    if ARGS.file != '':
        utils.save_matrix(LEARNER.weights, ARGS.file)
else:
    LEARNER.weights = utils.read_matrix(ARGS.load)


# Set up a server
APP = flask.Flask('Tanks', static_url_path='', static_folder='', template_folder='')
svec = np.zeros(NUM_TANKS + 1, dtype=float)
avec = np.zeros(1, dtype=int)
COUNT = 0       # number of steps taken since start of server

@APP.route('/')
def demo():
    svec[:-1] = LEARNER.random.rand(NUM_TANKS) * (ARGS.num_levels - 1)
    svec[-1] = LEARNER.random.randint(14)
    avec[:] = LEARNER.next_action(svec)
    return flask.render_template('demo.html', N=ARGS.num_levels, T=NUM_TANKS,
                                 L=[c.name[1:] for c in CAPACITORS])

@APP.route('/status/')
def status():
    global COUNT
    s = list(svec)                                  # cache last results
    a = list(avec)
    w = list(LEARNER.weights)
    if COUNT % ARGS.interval == 0:                  # re-learn at interval steps
        episodes = LEARNER.neighbours(svec)
        LEARNER.learn(episodes=episodes, verbose=True)
    COUNT += 1
    svec[:] = LEARNER.next_state(svec, avec)        # compute new results
    avec[:] = LEARNER.recommend(svec)
    action = RESISTORS[a[0]].name[1:].upper() + ' on'
    return flask.jsonify(levels=[str(i) for i in s],
                         action=action,
                         weights=[str(i) for i in w])   # return cached results

APP.run()