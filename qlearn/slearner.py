"""
This module defines the SLearner class. SLearner learns a policy over a
continuous state space defined by a set of state variables. For the initial
learning, however, it discretely samples state space to learn weights for a
functional approximation. See flearner for more details on approximation.

Because state-space is continuous, OFFLINE learning is not possible since it
cannot cache maximum q-values for each state reached during learning episodes.

The system is defined by a Simulator object (see linsim/simulate.py).

All learners expose the following interface:

* Instantiation with relevant parameters any any number of positional and
    keyword arguments.
* reward(state, action, next_state, **kwargs) which returns the reward for taking an
    action from some state.
* next_state(state, action, **kwargs) which returns the next state based on the
    current state and action.
* neighbours (state) which returns states adjacent to provided state.
* value(state) which returns the utility of a state and the following action
    what leads to that utility.
* qvalue(state, action) which returns value of a state-action pair, or an array
    of values of all actions from a state if action is not specified.
* learn(episodes, actions, **kwargs) which runs over multiple episodes to populate
    a utility function or matrix.
* recommend(state, **kwargs) which recommends an action based on the learned values
    depending on the exploration vs. exploitation setting of the learner.
* reset() which returns the value function/matrix to its initial state while
    keeping any learning parameters provided at instantiation.
"""

import numpy as np
try:
    from flearner import FLearner
except ImportError:
    from .flearner import FLearner



class SLearner(FLearner):
    """
    An SLearner learns policy from a Simulator over a continuous state-space.
    The space is descretely sampled for the learning process. All state/action
    representations are as vectors.

    Args:
        reward (func): A function that takes state, action, next state and
            returns the reward (float).
        simulator (Simulator): A Simulator instance that represents the
            environment.
        stateconverter (FlagGenerator): A FlagGenerator instance that can
            decode state number into state vectors and encode the reverse. For
            e.g if the state is defined by x,y coords it can encode (x, y) into
            a row index for the rmatrix, and decode the index(state number) into
            (x, y).
        actionconverter (FlagGenerator): Same as state converter but for actions.
        func (func): A function approximation for the value of a state/action.
            Returns the terms of the approximation as a numpy array. Signature:
                float = func(state_vec, action_vec, weights_vec)
            Where [state|action_weights]_vec are arrays. The returned array
            can be of any length, where each element is a combination of the
            state/action variables.
        dfunc (func): The derivative of func with respect to weights. Same
            input signature as func. Returns 'funcdim` elements in returned array.
        funcdim (int): The dimension of the weights to learn. Defaults to
            dimension of func.
        goal (list/tuple/set/array/function): Indices of goal states in rmatrix
            OR a function that accepts a state vector and returns true if goal.
        lrate (float): Learning rate for q-learning.
        discount (float): Discount factor for q-learning.
        policy (str): The action selection policy. Used durung learning/
            exploration to randomly select actions from a state. One of
            QLearner.[UNIFORM | GREEDY | SOFTMAX]. Default UNIFORM.
        depth (int): Max number of iterations in each learning episode. Defaults
            to number of states in stateconverter.
        steps (int): Number of steps (state transitions) to look ahead to
            calculate next estimate of value of state, action pair. Default=1.
        seed (int): A seed for all random number generation in instance. Default
            is None.
        stepsize (func): A function that takes a state and returns a number
            indicating the simulator step size. By default returns None.
        **kwargs: Any number of other keyword arguments. These are passed to
            simulator.run() when next_state() is called.

    Instance Attributes:
        goal (func): Takes a state number (int) and returns bool whether it is
            a goal state or not.
        mode/policy/lrate/discount/simulator/depth: Same as args.
        random (np.random.RandomState): A random number generator local to this
            instance.
        weights (ndarray): The coefficients of the function provided.
    """

    def __init__(self, reward, simulator, stateconverter, actionconverter, goal,
                 func, funcdim, dfunc, lrate=0.25, discount=1,
                 policy='uniform', depth=None, steps=1, seed=None,
                 stepsize=lambda x:None, **kwargs):
        if seed is None:
            self.random = np.random.RandomState()
        else:
            self.random = np.random.RandomState(seed)

        self.simulator = simulator

        self.lrate = lrate
        self.discount = discount
        self.depth = stateconverter.num_states if depth is None else depth
        self.steps = steps
        self.stepsize = stepsize

        self.funcdim = funcdim
        self.func = func
        self.dfunc = dfunc
        self.weights = np.ones(self.funcdim)

        self.stateconverter = stateconverter
        self.actionconverter = actionconverter
        self._avecs = [avec for avec in self.actionconverter]

        self._reward = reward
        self.set_goal(goal)
        self.set_action_selection_policy(policy, mode=SLearner.ONLINE, **kwargs)

    @property
    def num_states(self):
        return self.stateconverter.num_states

    @property
    def num_actions(self):
        return self.actionconverter.num_states


    def set_goal(self, goal):
        """
        Sets a function that checks if a state is a goal state or not.

        Args:
            goal (list/tuple/set/array/function): Goal state vectors.
                OR a function that accepts a state vector and returns true if
                goal.
        """
        if isinstance(goal, (np.ndarray, list, tuple, set)):
            # self._goals = set(goal)
            self.goal = lambda x: x in goal
        elif callable(goal):
            # self._goals = set([g for g in self.stateconverter if goal(g)])
            self.goal = goal
        else:
            raise TypeError('Provide goal as list/set/array/tuple/function.')


    def episodes(self, coverage=1., **kwargs):
        """
        Provides a sequence of states for learning episodes to start from.

        Args:
            coverage (float): Fraction of states to generate for episodes.
                Default= 1. Range [0, 1].

        Returns:
            A generator of of state vectors.
        """
        num = int(self.num_states * coverage)
        for _ in range(num):
            yield self.stateconverter.decode(self.random.choice(self.num_states))


    def reward(self, svec, avec, next_svec, **kwargs):
        return self._reward(svec, avec, next_svec)


    def next_state(self, svec, avec, **kwargs):
        """
        Uses a linsim.Simulator instance (or a compatible class) to find the
        next state vector. Forwards keyword arguments to the simulator.run
        function.
        """
        return self.simulator.run(state=svec, action=avec, **kwargs)


    def next_action(self, svec):
        return self._avecs[super().next_action(svec)]


    def neighbours(self, svec):
        """
        Returns a list of state vectors adjacent to provided state.

        Args:
            svec (ndarray/list/tuple): The state vector.

        Returns:
            A list of adjacent state vectors.
        """
        return [self.next_state(svec, avec) for avec in self._avecs]


    def value(self, state):
        """
        The value of state i.e. the expected rewards by being greedy with
        the value function.

        Args:
            state (int/list/array): Index of current state in [r|q]matrix
                (row index).

        Returns:
            A tuple of (float, action vector) representing value and the next
            most rewarding action vector.
        """
        ans = super().value(state)
        return (ans[0], self._avecs[ans[1]])


    def qvalue(self, svec, avec=None):
        """
        The q-value of state, action pair.

        Args:
            svec (ndarray/list/tuple): Vector of state variables.
            avec (ndarray/list/tuple): Vector of action variables.

        Returns:
            The qvalue of state,action if action is specified. Else returns the
            qvalues of all actions from a state (ndarray).
        """
        if avec is not None:
            return self.func(svec, avec, self.weights)
        else:
            return np.array([self.func(svec, a, self.weights)\
                    for a in self._avecs])


    def update(self, svec, avec, error):
        """
        Updates weights given state, action, and error in current and next
        value estimate.

        Args:
            svec (ndarray/list/tuple): Vector of state variables.
            avec (ndarray/list/tuple): Vector of action variables.
            error (float): Error term (current value - next estimate)
        """
        self.weights -= self.lrate * error * self.dfunc(svec, avec, self.weights)


    def recommend(self, svec):
        """
        Returns the action with the highest q value.

        Args:
            svec (ndarray/list/tuple): Vector of state variables.
        Returns:
            The action vector corresponding to the most valuable action.
        """
        return self.actionconverter.decode(super().recommend(svec))
