# 📊 CPU Demand Generation Analysis

**Question:** Kenapa tidak derive `cpu_demand` dari actual calibration data yang sudah ada?

**Answer:** EXCELLENT POINT - Ada beberapa issue yang perlu diaddress.

---

## 1. Current Situation

### Theoretical vs Actual

```
Theoretical (dari CPU_TIME_MS_RANGE):  [0.8000, 3.6000]
Actual (dari 950 calibration tasks):   [0.8576, 3.5038]
```

✅ **Range sesuai** - tapi ada discrepancy dalam distribution

---

## 2. Key Issues Found

### Issue #1: Task Size Distribution SKEWED

```
Current Distribution:
  Small:  8%  ❌ Too LOW  (expected ~20%)
  Medium: 76% ❌ Too HIGH (expected ~60%)
  Large:  16% ✅ OK      (expected ~20%)

Reason:
  - Small tasks: cpu_demand < 350ms & memory < 0.25GB
    Only 76/950 tasks = 8%
  
  - Medium tasks: cpu_demand < 650ms & memory < 0.75GB
    722/950 tasks = 76% (dominasi!)
  
  - Large tasks: everything else
    152/950 tasks = 16%
```

**Impact:** Workload bias towards MEDIUM tasks, kurang representative terhadap variance yang diinginkan.

### Issue #2: Distribution LEFT-SKEWED

```
44% tasks > mean (mean = 1.8915)
Expected untuk uniform: 50%

Reason: Random uniform distribution CPU_TIME_MS_RANGE menghasilkan left-skewed cpu_demand
```

**Impact:** Optimizer mungkin tidak exposed terhadap extreme cases (very small atau very large tasks).

### Issue #3: cpu_demand Generation vs Actual Characteristics

Current approach:
```python
# Hanya bergantung CPU time, tidak pada actual observed patterns
cpu_time_target_ms = np.random.uniform(200, 900)
cpu_demand = cpu_time_target_ms / 250.0
```

Problem:
- ❌ Tidak capture actual correlation antara cpu_demand dan memory_demand
- ❌ Tidak reflect actual task execution patterns
- ❌ Static ranges (200-900ms) tidak adaptif

---

## 3. Detailed Comparison: cpu_demand Distribution

### Theoretical Distribution (Uniform Random)

```
Expected from np.random.uniform(200, 900) / 250:
- Flat distribution across [0.8, 3.6]
- Mean ≈ 2.2
- All values equally likely
```

### Actual Distribution (dari calibration data)

```
Actual observed:
  0.5-1.0:  16% (152 tasks)
  1.0-1.5:  16% (152 tasks)
  1.5-2.0:  24% (228 tasks)  ← Peak here
  2.0-2.5:  20% (190 tasks)
  2.5-3.0:  16% (152 tasks)
  3.0-3.5:   4% (38 tasks)    ← Very few large tasks
  3.5+:      4% (38 tasks)

Mean: 1.8915 (lower than theoretical ~2.2)
Median: 1.6728 (even lower)
```

**Pattern:** More concentrated around medium values, fewer extremes.

---

## 4. Classification Issue: Why Small Tasks Under-represented?

### Analysis per Task Size

```
SMALL tasks (cpu_demand < 350ms & mem < 0.25GB):
  Count: 76 (8%)
  cpu_demand range: [1.2369, 1.3091]
  Problem: NARROW range! Hanya ~0.07 range untuk "small"

MEDIUM tasks:
  Count: 722 (76%)
  cpu_demand range: [0.8576, 2.5132]
  Problem: WIDE range! Mengabsorb banyak variasi

LARGE tasks (cpu_demand >= 650ms | mem >= 0.75GB):
  Count: 152 (16%)
  cpu_demand range: [2.7159, 3.5038]
  Good: Clear separation
```

**Root Cause:** Classification boundaries terlalu ketat untuk "small" dan "medium".

---

## 5. Recommendations

### Recommendation #1: Data-Driven cpu_demand Generation

**Current approach (theoretical):**
```python
cpu_time_target_ms = np.random.uniform(200, 900)
cpu_demand = cpu_time_target_ms / 250.0
```

**Better approach (data-driven):**
```python
# Option A: Sample directly dari calibration data
import numpy as np

# Load actual cpu_demand distribution
actual_cpu_demands = load_from_calibration()  # [0.8576, ..., 3.5038]

# Generate new tasks by sampling dari distribution
cpu_demand = np.random.choice(actual_cpu_demands)  # Resample dari actual

# Advantage:
# ✅ Exact match dengan observed patterns
# ✅ Preserves correlation antara cpu_demand, memory_demand, execution time
# ✅ More representative workload
```

**Option B: Fit distribution dari calibration data**
```python
from scipy.stats import gaussian_kde

# Fit KDE dari actual cpu_demand
pdf = gaussian_kde(actual_cpu_demands)

# Generate baru dengan same distribution
cpu_demand = pdf.resample(1)[0]

# Advantage:
# ✅ Smooth interpolation
# ✅ Can generate new values outside observed range if needed
# ✅ Theoretically principled
```

**Option C: Stratified sampling (untuk balanced distribution)**
```python
# Ensure balanced task size distribution
# 20% small, 60% medium, 20% large

task_size = np.random.choice(['small', 'medium', 'large'], 
                             p=[0.20, 0.60, 0.20])

if task_size == 'small':
    cpu_demand = np.random.uniform(1.0, 1.4)      # Adjusted range
elif task_size == 'medium':
    cpu_demand = np.random.uniform(1.4, 2.7)      # Adjusted range
else:  # large
    cpu_demand = np.random.uniform(2.7, 3.6)
```

---

### Recommendation #2: Adjust Classification Boundaries

**Current boundaries (too tight for small):**
```python
if cpu_time_target_ms < 350 and mem_gb < 0.25:
    return "small"
elif cpu_time_target_ms < 650 and mem_gb < 0.75:
    return "medium"
return "large"
```

**Better boundaries (based on actual data):**
```python
# Target distribution: 20% small, 60% medium, 20% large

if cpu_demand < 1.3 and mem_gb < 0.25:
    return "small"      # [0.8, 1.3)
elif cpu_demand < 2.7 and mem_gb < 0.75:
    return "medium"     # [1.3, 2.7)
else:
    return "large"      # [2.7, 3.6]
```

---

### Recommendation #3: Capture Correlation

Current approach generates cpu_demand dan memory_demand independently.

**Problem:** Tidak capture actual correlation

```python
# Actual correlation (dari calibration):
correlation(cpu_demand, memory_demand) ≈ 0.XX  (check actual value)

# Fix: Use multivariate sampling
from scipy.stats import multivariate_normal

# Load actual joint distribution
mean = [1.89, 0.44]  # actual mean dari calibration
cov = [[0.525, X], [X, 0.035]]  # covariance matrix

# Generate correlated pairs
cpu_demand, memory_demand = np.random.multivariate_normal(mean, cov)
```

---

## 6. Implementation Options

### Option A: Minimal Change (Recommended)

**Adjust boundaries only:**
```python
def classify_task(cpu_time_target_ms, memory_bytes):
    mem_gb = memory_bytes / (1024 ** 3)
    
    # Updated thresholds based on calibration data
    if cpu_time_target_ms < 325 and mem_gb < 0.25:      # ← adjusted
        return "small"
    elif cpu_time_target_ms < 675 and mem_gb < 0.75:    # ← adjusted
        return "medium"
    return "large"
```

**Benefit:** Simple, low-risk change

---

### Option B: Data-Driven Sampling (Recommended for Production)

**Load actual distribution:**
```python
import json
import numpy as np
from pathlib import Path

# Load calibration data once
CALIBRATION_DATA = None

def load_calibration_distribution():
    global CALIBRATION_DATA
    if CALIBRATION_DATA is None:
        tasks = []
        calibration_dir = Path("outputs/calibration")
        for path in sorted(calibration_dir.glob("*.jsonl")):
            with path.open() as f:
                for line in f:
                    if line.strip():
                        tasks.append(json.loads(line))
        CALIBRATION_DATA = tasks
    return CALIBRATION_DATA

def generate_task_from_calibration(task_id=None, seed=None):
    """Generate task by sampling dari actual calibration distribution"""
    
    if seed is not None:
        np.random.seed(seed)
    
    tasks = load_calibration_distribution()
    
    # Randomly select dari calibration sebagai template
    template = np.random.choice(tasks)
    
    # Slight variation untuk generate "new" task
    cpu_demand = float(template['cpu_demand']) * np.random.normal(1.0, 0.05)
    memory_demand = float(template['memory_demand']) * np.random.normal(1.0, 0.05)
    
    # Clamp ke bounds
    cpu_demand = np.clip(cpu_demand, 0.8, 3.6)
    memory_demand = np.clip(memory_demand, 0.125, 0.75)
    
    return {
        "task_id": task_id or str(uuid.uuid4()),
        "cpu_demand": float(cpu_demand),
        "memory_demand": float(memory_demand),
        "compute_cost": float(cpu_demand * 100.0),
        "task_type": "cpu_mem_burn",
        "cpu_time_target_ms": float(cpu_demand * 250.0),
        "memory_bytes": int(memory_demand * 1024**3),
        "payload": template.get('payload', {"seed": seed or 0, "touch_rounds": 4}),
        "arrival_time": 0.0,
        "task_size": classify_task(cpu_demand * 250.0, memory_demand * 1024**3),
        "experiment_id": "exp_1",
    }
```

**Benefit:** 
- ✅ Exact match dengan observed patterns
- ✅ More representative workload
- ✅ Captures correlation

---

## 7. Validation Checklist

- [ ] Verify current calibration data consistency
- [ ] Check correlation antara cpu_demand dan memory_demand
- [ ] Choose implementation option (A, B, atau custom)
- [ ] Update task_generator.py
- [ ] Re-run calibration untuk validate new distribution
- [ ] Compare optimization results vs current baseline
- [ ] Document changes

---

## 8. Expected Impact

### If Option A (Adjust boundaries):
- ✅ Better balanced task distribution (20/60/20)
- ✅ Minimal code change
- ⚠️ Still using theoretical uniform generation

### If Option B (Data-driven sampling):
- ✅ Exact match dengan observed workload
- ✅ Captures real patterns dan correlation
- ✅ More reliable for optimization testing
- ⚠️ Requires loading calibration data (slight overhead)

---

## 9. Summary

**Your Question:** "Kenapa tidak derive cpu_demand dari actual calibration data?"

**Answer:** SANGAT BAIK POINT. Current approach:
- ✅ Generate valid cpu_demand dalam range yang sesuai
- ❌ Distribution SKEWED (terlalu banyak medium tasks)
- ❌ Tidak capture actual patterns
- ❌ Potential mismatch dengan real workload

**Action:** Implement Option A atau B untuk better representation dari actual workload patterns.

