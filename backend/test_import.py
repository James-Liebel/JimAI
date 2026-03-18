import traceback
import sys
import warnings

warnings.filterwarnings(
    "ignore",
    message="Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater.",
    category=UserWarning,
)
try:
    import chromadb
    print("Success")
except Exception as e:
    with open("err.txt", "w") as f:
        traceback.print_exc(file=f)
