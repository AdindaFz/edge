# central/local_optimizers.py

import numpy as np

class DiffusionLocalOptimizer:

    def __init__(self, adjacency, gamma=0.1, max_steps=3):
        self.adjacency = adjacency
        self.gamma = gamma
        self.max_steps = max_steps

    def compute_load(self, assignments, cpu_demands, cpu_caps):
        N_NODES = len(cpu_caps)
        load = np.zeros(N_NODES)

        for i, node in enumerate(assignments):
            load[node] += cpu_demands[i]

        util = load / cpu_caps
        return util

    def refine(self, assignments, cpu_demands, cpu_caps):

        N_NODES = len(cpu_caps)

        for step in range(self.max_steps):

            util = self.compute_load(assignments, cpu_demands, cpu_caps)

            print(f"[DIFF] Step {step} | Util: {util}")

            mean_util = np.mean(util)

            for i in range(N_NODES):

                if util[i] <= mean_util:
                    continue

                neighbors = self.adjacency.get(i, [])
                if not neighbors:
                    continue

                j = min(neighbors, key=lambda x: util[x])

                tasks_i = np.where(assignments == i)[0]
                if len(tasks_i) == 0:
                    continue

                t = np.random.choice(tasks_i)

                assignments[t] = j

                delta = cpu_demands[t]
                util[i] -= delta / cpu_caps[i]
                util[j] += delta / cpu_caps[j]

        return assignments
