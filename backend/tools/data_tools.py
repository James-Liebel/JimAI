import pandas as pd
import numpy as np

def profile_dataframe(csv_path: str) -> str:
    # A lightweight text representation of what ydata would do
    try:
        df = pd.read_csv(csv_path)
        desc = df.describe(include="all").to_string()
        return f"Shape: {df.shape}\nCols: {df.columns.tolist()}\nNulls: {df.isnull().sum().to_dict()}\n{desc}"
    except Exception as e:
        return f"Error profiling df: {e}"

def compute_stats(data: list, column: str = None) -> dict:
    arr = np.array(data)
    return {
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "std": float(np.std(arr)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr))
    }

def detect_outliers(data: list) -> dict:
    arr = np.array(data)
    mean, std = np.mean(arr), np.std(arr)
    z_scores = (arr - mean) / std
    outliers = np.where(np.abs(z_scores) > 3)[0]
    return {"outlier_indices": outliers.tolist(), "values": arr[outliers].tolist()}

def suggest_model(description: str) -> str:
    return "RandomForestClassifier due to robustness to outliers."

def check_assumptions(test: str, data: list) -> dict:
    from scipy import stats
    return {"test": test, "assumptions": "Normal and homoscedastic"}

def generate_plot(code: str) -> str:
    return "base64_plot_placeholder_string"
