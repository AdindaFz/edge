import numpy as np
from central.simulation_model import energy_of_configuration, latency_of_configuration
import time

# =========================================================
# TABU + ENERGY FOCUS
# =========================================================
def hybrid_tabu_diff(
    cpu_demands,
    cpu_caps,
    mem_demands,
    mem_caps,
    latency_ms,
    node_powers,
    init_assign=None,
    TABU_MAX_ITER=300,
    TABU_TENURE=30,
    NUM_MOVES=70,
    diffusion=None,
    E_ref=None,
    L_ref=None,
    energy_weight=0.6
):

    N_tasks = len(cpu_demands)
    N_nodes = len(cpu_caps)

    if init_assign is not None:
        current_assign = init_assign.copy()
    else:
        current_assign = np.random.randint(0, N_nodes, size=N_tasks)

    gbest_assign = current_assign.copy()
    gbest_cost, _ = compute_total_cost_energy_focused(
        current_assign,
        cpu_demands,
        mem_demands,
        cpu_caps,
        mem_caps,
        latency_ms,
        node_powers,
        E_ref,
        L_ref,
        energy_weight=energy_weight
    )
    
    print(f"[INIT] Initial cost: {gbest_cost:.4f}, assignment: {np.bincount(current_assign)}")
    
    tabu_dict = {}
    no_improve_counter = 0
    history = {"obj": [], "time": []}
    start_time = time.perf_counter()

    for it in range(TABU_MAX_ITER):
        
        # ✅ COMPUTE LOAD ONCE
        load, cpu_util, mem_util = compute_node_utilization(
            current_assign, cpu_demands, cpu_caps, mem_demands, mem_caps
        )
        
        best_candidate = None
        best_candidate_cost = float("inf")
        best_move = None

        # ✅ GENERATE CANDIDATES
        for _ in range(NUM_MOVES):
            
            # Move type: 60% single, 40% swap (proven combination)
            if np.random.rand() < 0.6:
                # ===== SINGLE MOVE (weighted by inverse util) =====
                t = np.random.randint(0, N_tasks)
                
                # Weight by inverse utilization (prefer underloaded nodes)
                node_weights = 1.0 / (1.0 + cpu_util)
                node_weights /= node_weights.sum()
                
                new_node = np.random.choice(range(N_nodes), p=node_weights)
                
                if new_node == current_assign[t]:
                    continue
                
                trial_assign = current_assign.copy()
                trial_assign[t] = new_node
                move = ("single", t, new_node)
                
            else:
                # ===== SWAP MOVE (overload-aware) =====
                overloaded_nodes = np.where(cpu_util > 0.8)[0]
                underloaded_nodes = np.where(cpu_util < 0.6)[0]
                
                if len(overloaded_nodes) > 0 and len(underloaded_nodes) > 0:
                    # Prefer tasks on overloaded nodes
                    overloaded_tasks = [
                        idx for idx in range(N_tasks)
                        if current_assign[idx] in overloaded_nodes
                    ]
                    underloaded_tasks = [
                        idx for idx in range(N_tasks)
                        if current_assign[idx] in underloaded_nodes
                    ]
                    
                    if len(overloaded_tasks) > 0 and len(underloaded_tasks) > 0:
                        t1 = np.random.choice(overloaded_tasks)
                        t2 = np.random.choice(underloaded_tasks)
                    else:
                        continue
                else:
                    t1 = np.random.randint(0, N_tasks)
                    t2 = np.random.randint(0, N_tasks)
                    if t1 == t2:
                        continue
                
                trial_assign = current_assign.copy()
                trial_assign[t1], trial_assign[t2] = trial_assign[t2], trial_assign[t1]
                move = ("swap", min(t1, t2), max(t1, t2))
            
            # ===== EVALUATE =====
            trial_cost, _ = compute_total_cost_energy_focused(
                trial_assign,
                cpu_demands,
                mem_demands,
                cpu_caps,
                mem_caps,
                latency_ms,
                node_powers,
                E_ref,
                L_ref,
                energy_weight=energy_weight
            )
            
            # ===== TABU CHECK =====
            is_tabu = move in tabu_dict and tabu_dict[move] > it
            is_aspiration = trial_cost < gbest_cost  # Allow if better than best
            
            if (not is_tabu or is_aspiration) and trial_cost < best_candidate_cost:
                best_candidate_cost = trial_cost
                best_candidate = trial_assign.copy()
                best_move = move

        # ===== NO CANDIDATE? SKIP =====
        if best_candidate is None:
            no_improve_counter += 1
        else:
            # ===== UPDATE CURRENT =====
            current_assign = best_candidate.copy()
            tabu_dict[best_move] = it + TABU_TENURE
            
            # ===== UPDATE GLOBAL BEST =====
            if best_candidate_cost < gbest_cost:
                gbest_cost = best_candidate_cost
                gbest_assign = best_candidate.copy()
                no_improve_counter = 0
                print(f"[TABU] Iter {it} | Cost={gbest_cost:.4f} ✅")
            else:
                no_improve_counter += 1

        # ✅ DIVERSIFICATION (proven strategy)
        if no_improve_counter > 20:
            print(f"[SHAKE] Iter {it}: No improve for 20 iters, diversifying...")
            num_shake = max(1, int(0.2 * N_tasks))
            for _ in range(num_shake):
                t = np.random.randint(0, N_tasks)
                current_assign[t] = np.random.randint(0, N_nodes)
            no_improve_counter = 0

        # ✅ DIFFUSION (setiap 10 iters atau no_improve > 15)
        if diffusion is not None and (it % 10 == 0 or no_improve_counter > 15):
            refined = diffusion.refine(gbest_assign, cpu_demands, cpu_caps)
            refined_cost, _ = compute_total_cost_energy_focused(
                refined,
                cpu_demands,
                mem_demands,
                cpu_caps,
                mem_caps,
                latency_ms,
                node_powers,
                E_ref,
                L_ref,
                energy_weight=energy_weight
            )
            
            if refined_cost < gbest_cost:
                gbest_cost = refined_cost
                gbest_assign = refined.copy()
                print(f"[DIFF] Iter {it} | Cost={gbest_cost:.4f} ✅")
                no_improve_counter = 0

        # ===== LOGGING =====
        history["obj"].append(gbest_cost)
        history["time"].append(time.perf_counter() - start_time)

        if it % 10 == 0:
            print(f"[TABU+DIFF] Iter {it} | Cost={gbest_cost:.4f}")

    return gbest_assign, history


def compute_node_utilization(assignments, cpu_demands, cpu_caps, mem_demands, mem_caps):
    """Helper untuk compute load"""
    N_nodes = len(cpu_caps)
    cpu_used = np.zeros(N_nodes)
    mem_used = np.zeros(N_nodes)
    
    for t, node in enumerate(assignments):
        cpu_used[node] += cpu_demands[t]
        mem_used[node] += mem_demands[t]
    
    cpu_util = cpu_used / np.maximum(cpu_caps, 1e-6)
    mem_util = mem_used / np.maximum(mem_caps, 1e-6)
    
    return cpu_used, cpu_util, mem_util


def compute_total_cost_energy_focused(
    assignments,
    cpu_demands,
    mem_demands,
    cpu_caps,
    mem_caps,
    latency_ms,
    node_powers,  # ✅ ADD THIS
    E_ref=None,
    L_ref=None,
    energy_weight=0.8
):
    """
    ✅ Use REAL node power, not model power
    """

    # ======================
    # BASE METRICS
    # ======================
    N_nodes = len(cpu_caps)

    cpu_used = np.zeros(N_nodes)
    for t, node in enumerate(assignments):
        cpu_used[node] += cpu_demands[t]

    cpu_util = cpu_used / cpu_caps
    cpu_util = np.clip(cpu_util, 0, 2.0)

    # ✅ REAL ENERGY using node power
    total_energy = energy_of_configuration(
        assignments,
        cpu_demands,
        mem_demands,
        cpu_caps,
        mem_caps,
        node_powers=node_powers
    )

    # ======================
    # LATENCY (keep same)
    # ======================
    latency, _ = latency_of_configuration(
        assignments,
        cpu_demands,
        mem_demands,
        latency_ms,
        cpu_caps,
        mem_caps
    )

    # ======================
    # NORMALIZATION
    # ======================
    if E_ref is not None and L_ref is not None:
        energy_norm = total_energy / E_ref
        latency_norm = latency / L_ref
    else:
        energy_norm = total_energy
        latency_norm = latency

    # ======================
    # ✅ FINAL COST
    # ======================
    cost = (
        energy_weight * energy_norm +
        (1 - energy_weight) * latency_norm
    )

    return cost, cpu_util
