import numpy as np

class DiffusionLocalOptimizer:
    def __init__(self, adjacency, gamma=0.05, max_steps=5, node_powers=None):
        self.adjacency = adjacency
        self.gamma = gamma
        self.max_steps = max_steps
        self.node_powers = node_powers  # ✅ ADD THIS
    
    def refine(self, assignments, cpu_demands, cpu_caps):
        """
        ✅ Power-aware diffusion: smooth load tapi prefer low-power nodes
        """
        best_assign = assignments.copy()
        N_nodes = len(cpu_caps)
        N_tasks = len(cpu_demands)
        
        for step in range(self.max_steps):
            # Calculate current utilization
            cpu_used = np.zeros(N_nodes)
            for t, node in enumerate(best_assign):
                cpu_used[node] += cpu_demands[t]
            
            cpu_util = cpu_used / cpu_caps
            
            # For each task, try to move to neighbor with better energy
            for t in range(N_tasks):
                current_node = best_assign[t]
                current_util = cpu_util[current_node]
                
                # Get neighbors
                neighbors = self.adjacency[current_node]
                
                best_neighbor = current_node
                best_energy_contribution = float('inf')
                
                # ✅ Evaluate each neighbor
                for neighbor in neighbors:
                    neighbor_util = cpu_util[neighbor]
                    
                    # Skip if neighbor is over-capacity
                    if neighbor_util + cpu_demands[t] / cpu_caps[neighbor] > 1.2:
                        continue
                    
                    # ✅ Consider BOTH utilization AND power
                    # Energy contribution = power * util
                    if self.node_powers is not None:
                        energy_current = self.node_powers[current_node] * current_util
                        energy_neighbor = self.node_powers[neighbor] * neighbor_util
                    else:
                        energy_current = current_util
                        energy_neighbor = neighbor_util
                    
                    # Prefer neighbor jika energy lebih rendah
                    if energy_neighbor < best_energy_contribution:
                        best_energy_contribution = energy_neighbor
                        best_neighbor = neighbor
                
                # Move jika ada improvement
                if best_neighbor != current_node:
                    best_assign[t] = best_neighbor
                    cpu_used[current_node] -= cpu_demands[t]
                    cpu_used[best_neighbor] += cpu_demands[t]
                    cpu_util = cpu_used / cpu_caps
        
        return best_assign
