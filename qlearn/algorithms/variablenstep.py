"""
An implementation of the variable n-step tree backup algorithm. Where the current
value of a state/action pair is updated by the discounted expected reward of
choosing n-actions from the current state. If n=1, then it is QLearning.

The size of a step can be a function of the current state.

All learning algorithms should be able to learn from a single state/action pair.
All learning algorithms return a tuple of lists:
    [list of states traversed after the initial state, including final state],
    [list of actions taken to traverse states, starting with the first action]
"""


import numpy as np


def variablenstep(self, state, action):
    """
    Begins learning procedure over all (state, action) pairs. Calculates errors
    between last and current estimation of q-value and calls self.update to
    modify policy.
    Implements the n-step Tree Backup algorithm which is a variation of
    QLearning. The algorithm is modified to allow for variable step sizes.
    Compatible with integer and vector representation of states and actions.
    See Reinforcement Learning - an Introduction by Sutton/Barto (Ch. 7)

    Args:
        self (QLearner): A reference to the calling QLearner object or a
            subclass.
        state (int/list): State to begin learning episode from.
        action (int/list): Action to take from that state. If None, choose one
            from policy.
    Returns:
        A tuple of:
        - The history of N states traversed after the provided state.
        - The history of N actions taken after the provided state.
    """

    T = np.inf      # termination time (i.e. terminal state)
    tau = 0         # time of state being updated
    t = 0           # time from beginning of episode
    delta = []      # error in current and next value estimate at time t
    Q = []          # history of Q-values of taken actions
    A = []          # history of actions taken for n-step lookahead
    S = [state]     # history of states taken
    pi = [1]        # history of action probabilities for each state

    A.append(self.next_action(state) if action is None else action)
    Q.append(self.qvalue(state, A[-1]))

    # Loop from start of episode until the state before terminal state
    while tau <= T-1 and t < self.depth:
        # The algorithm looks n-steps ahead of the state in the episode
        # being updated. If a terminal state comes before n-steps, it
        # stops looking ahead.
        if t < T:
            action = A[-1]                          # current action
            state = S[-1]                           # current state
            naction = self.next_action(state)       # next action
            step = self.stepsize(state)             # size of lookahead
            nstate = self.next_state(state, action, stepsize=step) # next state
            cqvalue = self.qvalue(state, action)    # current Q-value
            nqvalue = self.qvalue(nstate, naction)  # next Q-value

            A.append(naction)
            S.append(nstate)
            Q.append(nqvalue)

            reward = self.reward(state, action, nstate, stepsize=step)
            aprobs = self.a_probs(nstate)
            # For QLearner subclasses with vector representation,
            # naction cannot be used as an index
            if isinstance(naction, (int, np.integer)):
                pi.append(aprobs[naction])
            else:
                pi.append(aprobs[self.actionconverter.encode(naction)])

            if self.goal(nstate):   # Episode stops look-ahead by
                T = t + 1           # updating T from infinity to t+1
                delta.append(reward - cqvalue)
            else:
                delta.append(
                    reward \
                    + self.discount * np.dot(aprobs, self.qvalue(nstate))\
                    - cqvalue
                    )
        # In the second step, the algorithm updates a state's value
        # using the errors/rewards computed from the look-ahead.
        tau = t - self.steps + 1 # tau trails look-ahead (t) by n-steps
        if tau >= 0:
            E = 1
            G = Q[tau]  # G is the expected return using n-step lookahead
            # Iterating from current state to n-steps ahead or terminal
            # state (whichever's closer), computes the n-step error
            # and updates q-matrix accordingly.
            for k in range(tau, min(tau + self.steps, T)):
                G += E * delta[k]
                E = self.discount * E * pi[k+1]
            self.update(S[tau], A[tau], self.qvalue(S[tau], A[tau]) - G)
        t += 1
    return S[1:], A
